from datetime import datetime
from functools import wraps
from urllib.parse import unquote, urlencode, urlsplit

from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from config import DevelopmentConfig
from connections import (
    ConnectionError,
    accept_request,
    cancel_request,
    connection_lists,
    decline_request,
    relationship_between,
    relationship_state,
    remove_connection,
    send_request,
    states_for_users,
)
from discovery import discover_profiles, parse_filters, public_profile
from forms import CommunityPlanForm, ConnectionActionForm, ConnectionRequestForm, LoginForm, LogoutForm, MessageForm, NotificationActionForm, PlanActionForm, ProfileForm, RegistrationForm, RemoveProfilePhotoForm, SafetyActionForm, UserReportForm
from messaging import (
    MessagingError,
    accessible_conversation,
    active_connection_between,
    format_message_time,
    inbox_page,
    mark_conversation_read,
    message_page,
    message_preview,
    other_participant,
    send_message,
    start_conversation,
    unread_conversation_count,
)
from models import ConnectionIntent, ConnectionRequest, Interest, Language, Profile, User, db
from community_plans import (
    CATEGORY_LABELS,
    PLAN_CATEGORIES,
    PlanError,
    browse_plans,
    cancel_plan,
    create_plan,
    edit_plan,
    join_plan,
    leave_plan,
    my_plans,
    participant_ids,
    plan_details,
    plan_is_past,
    plan_state,
    remove_participant,
)
from profile_data import CONNECTION_INTENTS, GENDER_CHOICES, INTERESTS, LANGUAGES, country_choices, country_name, slugify_interest
from profile_photo_storage import PROFILE_PHOTO_KEY_PATTERN, build_profile_photo_storage
from profile_photos import ProfilePhotoError, generate_profile_photo_key, process_profile_photo
from notifications import (
    NotificationError,
    destination_for,
    format_notification_time,
    mark_all_read,
    mark_read,
    notification_page,
    notify_connection_accepted,
    notify_connection_request,
    notify_new_message,
    notify_plan_cancelled,
    notify_plan_join,
    notify_plan_leave,
    notify_plan_removed,
    owned_notification,
    unread_notification_count,
)
from timezones import DEFAULT_TIMEZONE, format_plan_datetime, timezone_choices, utc_to_local
from safety import SafetyError, block_user, blocked_users, is_blocked_pair, report_user, unblock_user

app = Flask(__name__)
app.config.from_object(DevelopmentConfig)

# Extensions are initialized without creating tables; schema changes use migrations.
db.init_app(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)


@app.errorhandler(413)
def upload_too_large(_error):
    """Convert oversized multipart requests into safe, friendly feedback."""
    if g.get("user") is not None:
        flash("Profile photos must be 5 MB or smaller.", "error")
        return redirect(url_for("edit_profile"))
    return "The uploaded file is too large.", 413


@app.before_request
def load_current_user():
    """Load the signed-in user once per request without storing model data in the session."""
    user_id = session.get("user_id")
    g.user = db.session.get(User, user_id) if user_id is not None else None

    if user_id is not None and g.user is None:
        session.clear()


@app.context_processor
def inject_template_context():
    """Make common page context available without duplicating route logic."""
    received_count = 0
    unread_count = 0
    notification_count = 0
    if g.user is not None:
        received_count = db.session.scalar(
            db.select(db.func.count(ConnectionRequest.id)).where(
                ConnectionRequest.recipient_id == g.user.id,
                ConnectionRequest.status == "pending",
            )
        ) or 0
        unread_count = unread_conversation_count(db.session, g.user.id)
        notification_count = unread_notification_count(db.session, g.user.id)
    return {
        "current_year": datetime.now().year,
        "current_user": g.user,
        "country_name": country_name,
        "received_connection_count": received_count,
        "unread_conversation_count": unread_count,
        "unread_notification_count": notification_count,
    }


def configure_profile_choices(form):
    """Populate reusable catalogue choices without coupling forms to the database."""
    form.languages.choices = [(item.id, item.name) for item in db.session.scalars(db.select(Language).order_by(Language.name))]
    form.interests.choices = [
        (item.id, item.name) for item in db.session.scalars(db.select(Interest).order_by(Interest.category, Interest.name))
    ]
    form.connection_intents.choices = [
        (item.id, item.name) for item in db.session.scalars(db.select(ConnectionIntent).order_by(ConnectionIntent.id))
    ]


def selected_records(model, identifiers):
    """Resolve submitted catalogue IDs through SQLAlchemy, never trusting raw values."""
    identifiers = set(identifiers or [])
    return list(db.session.scalars(db.select(model).where(model.id.in_(identifiers)))) if identifiers else []


def is_safe_next_url(target):
    """Allow only absolute-path redirects that remain inside this application."""
    if not target:
        return False

    decoded_target = unquote(target)
    parsed_target = urlsplit(decoded_target)
    return (
        not parsed_target.scheme
        and not parsed_target.netloc
        and decoded_target.startswith("/")
        and not decoded_target.startswith("//")
        and "\\" not in decoded_target
    )


def login_required(view):
    """Redirect anonymous visitors to login while preserving a safe local destination."""
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "info")
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapped_view


def profile_complete_required(view):
    """Reusable Sprint 6 gate for features that require a complete profile."""
    @login_required
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user.profile is None or not g.user.profile.is_complete:
            flash("Complete your profile before continuing.", "info")
            return redirect(url_for("edit_profile"))
        return view(*args, **kwargs)

    return wrapped_view


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).where(User.email == form.email.data))

        if user is not None and user.check_password(form.password.data):
            session.clear()
            session.permanent = form.remember_me.data
            session["user_id"] = user.id
            flash(f"Welcome back, {user.first_name}.", "success")

            next_url = request.args.get("next")
            return redirect(next_url if is_safe_next_url(next_url) else url_for("dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html", form=form)


@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        try:
            existing_user = db.session.scalar(db.select(User).where(User.email == email))
            if existing_user:
                form.email.errors.append("An account with this email already exists.")
            else:
                user = User(
                    first_name=form.first_name.data.strip(),
                    last_name=form.last_name.data.strip(),
                    email=email,
                    date_of_birth=form.date_of_birth.data,
                )
                user.set_password(form.password.data)
                db.session.add(user)
                db.session.commit()
                flash("Your Friendly account has been created. You can now log in.", "success")
                return redirect(url_for("login"))
        except SQLAlchemyError:
            db.session.rollback()
            # Log diagnostic details server-side without including submitted credentials.
            app.logger.exception("Registration failed because of a database error.")
            flash("We couldn't create your account right now. Please try again.", "error")
    return render_template("register.html", form=form)


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        logout_form=LogoutForm(),
        profile=g.user.profile,
    )


@app.route("/discover")
@profile_complete_required
def discover():
    """Show a filtered, transparently ranked page of eligible local people."""
    languages = list(db.session.scalars(db.select(Language).order_by(Language.name)))
    interests = list(db.session.scalars(db.select(Interest).order_by(Interest.category, Interest.name)))
    intentions = list(db.session.scalars(db.select(ConnectionIntent).order_by(ConnectionIntent.id)))
    catalogues = {
        "languages": {item.id for item in languages},
        "interests": {item.id for item in interests},
        "intentions": {item.id for item in intentions},
    }
    gender_options = dict(GENDER_CHOICES)
    filters = parse_filters(request.args, catalogues, set(gender_options))
    try:
        requested_page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        requested_page = 1
    results = discover_profiles(db.session, g.user.profile, filters, requested_page)
    relationship_states = states_for_users(
        db.session,
        g.user.id,
        [result.profile.user_id for result in results.items],
    )

    def page_url(number):
        query = [*filters.query_items(), ("page", number)]
        return f"{url_for('discover')}?{urlencode(query)}"

    return render_template(
        "discover.html",
        results=results,
        filters=filters,
        languages=languages,
        interests=interests,
        intentions=intentions,
        gender_options=gender_options,
        page_url=page_url,
        relationship_states=relationship_states,
    )


@app.route("/people/<int:user_id>")
@login_required
def person_profile(user_id):
    """Render only another member's deliberately public profile fields."""
    if user_id == g.user.id:
        return redirect(url_for("profile"))
    if is_blocked_pair(db.session, g.user.id, user_id):
        abort(404)
    relationship = relationship_between(db.session, g.user.id, user_id)
    # Pending and established relationships remain viewable if the other
    # member later pauses new requests. Discovery still requires openness.
    profile_record = public_profile(
        db.session,
        user_id,
        require_open=not (relationship and relationship.status in {"pending", "accepted"}),
    )
    if profile_record is None:
        abort(404)
    return render_template(
        "person_profile.html",
        profile=profile_record,
        gender_labels=dict(GENDER_CHOICES),
        relationship_state=relationship_state(g.user.id, user_id, relationship),
        safety_form=SafetyActionForm(),
    )


@app.route("/people/<int:user_id>/connect", methods=["GET", "POST"])
@profile_complete_required
def connect_person(user_id):
    """Confirm and create a connection request without trusting client identity."""
    if user_id == g.user.id:
        abort(400)
    if is_blocked_pair(db.session, g.user.id, user_id):
        abort(404)
    relationship = relationship_between(db.session, g.user.id, user_id)
    # Existing pending/accepted relationships remain viewable if someone later
    # pauses new requests; discovery eligibility itself still requires openness.
    profile_record = public_profile(
        db.session,
        user_id,
        require_open=not (relationship and relationship.status in {"pending", "accepted"}),
    )
    if profile_record is None:
        abort(404)
    state = relationship_state(g.user.id, user_id, relationship)
    if state.key == "received":
        flash("You already have a connection request from this person.", "info")
        return redirect(url_for("connections", tab="received"))
    if state.key != "available":
        flash(state.label, "info")
        return redirect(url_for("person_profile", user_id=user_id))

    form = ConnectionRequestForm()
    if form.validate_on_submit():
        try:
            relationship = send_request(db.session, g.user, user_id, form.introduction.data)
            notify_connection_request(db.session, relationship)
            db.session.commit()
            flash(f"Connection request sent to {profile_record.user.first_name}.", "success")
            return redirect(url_for("person_profile", user_id=user_id))
        except ConnectionError as error:
            db.session.rollback()
            flash(error.message, "info")
            return redirect(url_for("person_profile", user_id=user_id))
        except IntegrityError:
            db.session.rollback()
            flash("That connection state changed. Refresh and try again.", "info")
            return redirect(url_for("person_profile", user_id=user_id))
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Connection request failed because of a database error.")
            flash("We couldn't send that request right now. Please try again.", "error")
            return redirect(url_for("person_profile", user_id=user_id))
    return render_template("connect.html", form=form, profile=profile_record)


@app.route("/connections")
@login_required
def connections():
    sections = connection_lists(db.session, g.user.id)
    tab = request.args.get("tab", "connections")
    if tab not in sections:
        tab = "connections"
    return render_template(
        "connections.html",
        sections=sections,
        active_tab=tab,
        action_form=ConnectionActionForm(),
        safety_form=SafetyActionForm(),
    )


@app.post("/people/<int:user_id>/block")
@login_required
def block_person(user_id):
    form = SafetyActionForm()
    if not form.validate_on_submit():
        abort(400)
    if user_id == g.user.id:
        abort(400)
    try:
        block_user(db.session, g.user.id, user_id)
        db.session.commit()
        flash("This person has been blocked. Your previous connection and future plan participation were removed.", "success")
    except SafetyError as error:
        db.session.rollback()
        if error.code == "not_found":
            abort(404)
        flash(error.message, "info")
    except (IntegrityError, SQLAlchemyError):
        db.session.rollback()
        app.logger.exception("Blocking failed because of a database error.")
        flash("We couldn't complete that safety action right now. Please try again.", "error")
    return redirect(url_for("blocked_people"))


@app.post("/people/<int:user_id>/unblock")
@login_required
def unblock_person(user_id):
    form = SafetyActionForm()
    if not form.validate_on_submit():
        abort(400)
    if user_id == g.user.id or db.session.get(User, user_id) is None:
        abort(404)
    try:
        unblock_user(db.session, g.user.id, user_id)
        db.session.commit()
        flash("This person has been unblocked. Previous connections are not restored automatically.", "success")
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Unblocking failed because of a database error.")
        flash("We couldn't complete that safety action right now. Please try again.", "error")
    return redirect(url_for("blocked_people"))


@app.get("/settings/blocked-users")
@login_required
def blocked_people():
    return render_template("blocked_users.html", blocks=blocked_users(db.session, g.user.id), form=SafetyActionForm())


@app.route("/people/<int:user_id>/report", methods=["GET", "POST"])
@login_required
def report_person(user_id):
    if user_id == g.user.id:
        abort(400)
    target = db.session.get(User, user_id)
    if target is None or target.profile is None or is_blocked_pair(db.session, g.user.id, user_id):
        abort(404)
    form = UserReportForm()
    if form.validate_on_submit():
        try:
            report_user(db.session, g.user.id, user_id, form.reason.data, form.details.data)
            db.session.commit()
            flash("Thanks. Your report has been submitted for review.", "success")
            return redirect(url_for("person_profile", user_id=user_id))
        except SafetyError as error:
            db.session.rollback()
            getattr(form, error.code, form.reason).errors.append(error.message)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("A private report could not be stored.")
            flash("We couldn't submit that report right now. Please try again.", "error")
    return render_template("report_user.html", form=form, person=target)


def _connection_transition(action, relationship_id, success_message, tab, *, notifier=None):
    form = ConnectionActionForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        relationship = action(db.session, relationship_id, g.user.id)
        if notifier is not None:
            notifier(db.session, relationship)
        db.session.commit()
        flash(success_message, "success")
    except ConnectionError as error:
        db.session.rollback()
        flash(error.message, "info")
    except IntegrityError:
        db.session.rollback()
        flash("That connection state changed. Refresh and try again.", "info")
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Connection transition failed because of a database error.")
        flash("We couldn't update that connection right now. Please try again.", "error")
    return redirect(url_for("connections", tab=tab))


@app.post("/connections/<int:relationship_id>/accept")
@login_required
def accept_connection(relationship_id):
    return _connection_transition(accept_request, relationship_id, "You are now connected.", "connections", notifier=notify_connection_accepted)


@app.post("/connections/<int:relationship_id>/decline")
@login_required
def decline_connection(relationship_id):
    return _connection_transition(decline_request, relationship_id, "The request has been removed.", "received")


@app.post("/connections/<int:relationship_id>/cancel")
@login_required
def cancel_connection(relationship_id):
    return _connection_transition(cancel_request, relationship_id, "Your request has been cancelled.", "sent")


@app.post("/connections/<int:relationship_id>/remove")
@login_required
def remove_connection_route(relationship_id):
    return _connection_transition(remove_connection, relationship_id, "The connection has been removed.", "connections")


def _positive_page_argument(default=None):
    raw_page = request.args.get("page")
    if raw_page is None:
        return default
    try:
        return max(1, int(raw_page))
    except (TypeError, ValueError):
        return 1


def _configure_plan_form(form):
    form.category.choices = list(PLAN_CATEGORIES)
    form.country_code.choices = country_choices()


def _plan_form_data(form):
    return {
        "title": form.title.data,
        "category": form.category.data,
        "description": form.description.data,
        "country_code": form.country_code.data,
        "city": form.city.data,
        "starts_at": form.starts_at.data,
        "meeting_place_text": form.meeting_place_text.data,
        "capacity": form.capacity.data,
        "timezone": form.timezone.data,
    }


@app.get("/plans")
@profile_complete_required
def plans():
    categories = set(request.args.getlist("category")) & set(CATEGORY_LABELS)
    page = browse_plans(db.session, g.user.profile, _positive_page_argument(1), categories)
    return render_template(
        "plans.html",
        plans_page=page,
        categories=PLAN_CATEGORIES,
        selected_categories=categories,
        category_labels=CATEGORY_LABELS,
        plan_state=plan_state,
        format_plan_datetime=format_plan_datetime,
    )


@app.route("/plans/create", methods=["GET", "POST"])
@profile_complete_required
def create_community_plan():
    form = CommunityPlanForm()
    _configure_plan_form(form)
    if request.method == "GET":
        form.country_code.data = g.user.profile.discovery_country_code
        form.city.data = g.user.profile.discovery_city
        form.capacity.data = 6
        form.timezone.data = DEFAULT_TIMEZONE
    if form.validate_on_submit():
        try:
            plan = create_plan(db.session, g.user, _plan_form_data(form))
            db.session.commit()
            flash("Your community plan is ready.", "success")
            return redirect(url_for("community_plan", plan_id=plan.id))
        except PlanError as error:
            db.session.rollback()
            getattr(form, error.code, form.starts_at).errors.append(error.message)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Community plan creation failed because of a database error.")
            flash("We couldn't create that plan right now. Please try again.", "error")
    return render_template("plan_form.html", form=form, editing=False, timezone_choices=timezone_choices())


@app.get("/plans/mine")
@login_required
def my_community_plans():
    return render_template(
        "my_plans.html",
        sections=my_plans(db.session, g.user.id),
        category_labels=CATEGORY_LABELS,
        plan_state=plan_state,
        format_plan_datetime=format_plan_datetime,
    )


@app.get("/plans/<int:plan_id>")
@login_required
def community_plan(plan_id):
    plan = plan_details(db.session, plan_id)
    if plan is None:
        abort(404)
    ids = participant_ids(plan)
    return render_template(
        "plan_detail.html",
        plan=plan,
        participant_ids=ids,
        is_participant=g.user.id in ids,
        is_host=g.user.id == plan.creator_id,
        state=plan_state(plan, len(ids)),
        category_label=CATEGORY_LABELS.get(plan.category, "Other"),
        action_form=PlanActionForm(),
        format_plan_datetime=format_plan_datetime,
    )


@app.route("/plans/<int:plan_id>/edit", methods=["GET", "POST"])
@login_required
def edit_community_plan(plan_id):
    plan = plan_details(db.session, plan_id)
    if plan is None or plan.creator_id != g.user.id:
        abort(404)
    if plan.status != "active" or plan_is_past(plan):
        flash("Past or cancelled plans cannot be edited.", "info")
        return redirect(url_for("community_plan", plan_id=plan.id))
    form = CommunityPlanForm(obj=plan)
    _configure_plan_form(form)
    if request.method == "GET":
        form.starts_at.data = utc_to_local(plan.starts_at, plan.timezone).replace(tzinfo=None)
        form.timezone.data = plan.timezone
    if form.validate_on_submit():
        try:
            edit_plan(db.session, plan.id, g.user.id, _plan_form_data(form))
            db.session.commit()
            flash("Your plan has been updated.", "success")
            return redirect(url_for("community_plan", plan_id=plan.id))
        except PlanError as error:
            db.session.rollback()
            getattr(form, error.code, form.capacity).errors.append(error.message)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Community plan editing failed because of a database error.")
            flash("We couldn't update that plan right now. Please try again.", "error")
    return render_template("plan_form.html", form=form, editing=True, plan=plan, timezone_choices=timezone_choices())


def _plan_transition(action, plan_id, success_message, *, participant_id=None, notifier=None):
    form = PlanActionForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        if participant_id is None:
            plan = action(db.session, plan_id, g.user.id)
        else:
            plan = action(db.session, plan_id, participant_id, g.user.id)
        if notifier is not None:
            if participant_id is None:
                notifier(db.session, plan, g.user.id)
            else:
                notifier(db.session, plan, participant_id, g.user.id)
        db.session.commit()
        flash(success_message, "success")
    except PlanError as error:
        db.session.rollback()
        if error.code == "not_found":
            abort(404)
        flash(error.message, "info")
    except IntegrityError:
        db.session.rollback()
        flash("That plan changed while you were joining. Please try again.", "info")
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Community plan transition failed because of a database error.")
        flash("We couldn't update that plan right now. Please try again.", "error")
    return redirect(url_for("community_plan", plan_id=plan_id))


@app.post("/plans/<int:plan_id>/join")
@profile_complete_required
def join_community_plan(plan_id):
    return _plan_transition(join_plan, plan_id, "You joined the plan.", notifier=notify_plan_join)


@app.post("/plans/<int:plan_id>/leave")
@login_required
def leave_community_plan(plan_id):
    return _plan_transition(leave_plan, plan_id, "You left the plan.", notifier=notify_plan_leave)


@app.post("/plans/<int:plan_id>/cancel")
@login_required
def cancel_community_plan(plan_id):
    return _plan_transition(cancel_plan, plan_id, "The plan has been cancelled.", notifier=notify_plan_cancelled)


@app.post("/plans/<int:plan_id>/participants/<int:user_id>/remove")
@login_required
def remove_plan_participant(plan_id, user_id):
    return _plan_transition(remove_participant, plan_id, "The participant has been removed.", participant_id=user_id, notifier=notify_plan_removed)


@app.get("/messages")
@login_required
def messages():
    """Show one efficient, paginated inbox row per private conversation."""
    page = inbox_page(db.session, g.user.id, _positive_page_argument(1))
    return render_template(
        "messages.html",
        conversations=page,
        message_preview=message_preview,
        format_message_time=format_message_time,
    )


@app.get("/messages/start/<int:user_id>")
@login_required
def start_message_conversation(user_id):
    """Lazily create the canonical conversation only for an active connection."""
    try:
        conversation = start_conversation(db.session, g.user.id, user_id)
        db.session.commit()
        return redirect(url_for("conversation", conversation_id=conversation.id))
    except MessagingError as error:
        db.session.rollback()
        if error.code in {"not_found", "self"}:
            abort(404)
        flash(error.message, "info")
        return redirect(url_for("connections"))
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Conversation creation failed because of a database error.")
        flash("We couldn't open that conversation right now. Please try again.", "error")
        return redirect(url_for("connections"))


@app.get("/messages/<int:conversation_id>")
@login_required
def conversation(conversation_id):
    """Render private history and mark messages received by this member as read."""
    try:
        conversation_record = accessible_conversation(db.session, conversation_id, g.user.id)
    except MessagingError:
        abort(404)
    other = other_participant(conversation_record, g.user.id)
    blocked = is_blocked_pair(db.session, g.user.id, other.id)
    can_send = active_connection_between(db.session, g.user.id, other.id) and not blocked
    mark_conversation_read(db.session, conversation_record.id, g.user.id)
    db.session.commit()
    page = message_page(db.session, conversation_record.id, _positive_page_argument())
    return render_template(
        "conversation.html",
        conversation=conversation_record,
        other=other,
        messages_page=page,
        can_send=can_send,
        blocked=blocked,
        form=MessageForm(),
        format_message_time=format_message_time,
    )


@app.post("/messages/<int:conversation_id>/send")
@login_required
def send_conversation_message(conversation_id):
    """Persist a plain-text message with its sender derived only from the session."""
    form = MessageForm()
    if not form.validate_on_submit():
        flash(form.body.errors[0] if form.body.errors else "Check your message and try again.", "error")
        return redirect(url_for("conversation", conversation_id=conversation_id))
    try:
        message = send_message(db.session, conversation_id, g.user.id, form.body.data)
        conversation_record = accessible_conversation(db.session, conversation_id, g.user.id)
        recipient_id = conversation_record.user_high_id if conversation_record.user_low_id == g.user.id else conversation_record.user_low_id
        notify_new_message(db.session, message, conversation_record, recipient_id)
        db.session.commit()
    except MessagingError as error:
        db.session.rollback()
        if error.code == "not_found":
            abort(404)
        flash(error.message, "info")
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Private message failed because of a database error.")
        flash("We couldn't send that message right now. Please try again.", "error")
    return redirect(url_for("conversation", conversation_id=conversation_id))


@app.get("/notifications")
@login_required
def notifications():
    """Show only the signed-in member's paginated activity history."""
    page = notification_page(db.session, g.user.id, _positive_page_argument(1))
    return render_template(
        "notifications.html",
        notifications_page=page,
        action_form=NotificationActionForm(),
        format_notification_time=format_notification_time,
    )


def _notification_form_or_400():
    form = NotificationActionForm()
    if not form.validate_on_submit():
        abort(400)


@app.post("/notifications/<int:notification_id>/open")
@login_required
def open_notification(notification_id):
    """POST marks only owned activity read, then redirects to a controlled route."""
    _notification_form_or_400()
    try:
        notification = owned_notification(db.session, notification_id, g.user.id)
        destination = destination_for(db.session, notification, g.user.id)
        mark_read(db.session, notification.id, g.user.id)
        db.session.commit()
        return redirect(destination)
    except NotificationError:
        db.session.rollback()
        abort(404)


@app.post("/notifications/<int:notification_id>/read")
@login_required
def read_notification(notification_id):
    _notification_form_or_400()
    try:
        mark_read(db.session, notification_id, g.user.id)
        db.session.commit()
    except NotificationError:
        db.session.rollback()
        abort(404)
    return redirect(url_for("notifications"))


@app.post("/notifications/read-all")
@login_required
def read_all_notifications():
    _notification_form_or_400()
    mark_all_read(db.session, g.user.id)
    db.session.commit()
    return redirect(url_for("notifications"))


@app.route("/profile")
@login_required
def profile():
    if g.user.profile is None or g.user.date_of_birth is None:
        flash("Complete your profile so Friendly can help you find your community.", "info")
        return redirect(url_for("edit_profile"))
    return render_template(
        "profile.html",
        profile=g.user.profile,
        gender_labels=dict(GENDER_CHOICES),
    )


def profile_photo_storage():
    """Resolve the configured backend at use time so tests can isolate storage."""
    return build_profile_photo_storage(app.config)


@app.route("/profile/photo/<path:key>")
def profile_photo(key):
    """Deliver only safe object keys currently attached to legitimate profiles."""
    if not PROFILE_PHOTO_KEY_PATTERN.fullmatch(key):
        abort(404)
    exists = db.session.scalar(db.select(Profile.id).where(Profile.profile_photo_key == key))
    if exists is None:
        abort(404)
    storage = profile_photo_storage()
    if not storage.exists(key):
        abort(404)
    try:
        stored_photo = storage.open(key)
    except OSError:
        abort(404)
    return send_file(stored_photo, mimetype="image/webp", max_age=31536000, download_name="profile.webp")


@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    profile_record = g.user.profile
    form = ProfileForm(obj=profile_record)
    configure_profile_choices(form)

    if request.method == "GET":
        form.date_of_birth.data = g.user.date_of_birth
        if profile_record:
            form.languages.data = [item.id for item in profile_record.languages]
            form.interests.data = [item.id for item in profile_record.interests]
            form.connection_intents.data = [item.id for item in profile_record.connection_intents]

    if form.validate_on_submit():
        new_photo_key = None
        old_photo_key = profile_record.profile_photo_key if profile_record else None
        storage = profile_photo_storage()
        try:
            if form.profile_photo.data and form.profile_photo.data.filename:
                processed_photo = process_profile_photo(
                    form.profile_photo.data,
                    app.config["MAX_PROFILE_PHOTO_SIZE"],
                    {
                        "x": form.photo_crop_x.data,
                        "y": form.photo_crop_y.data,
                        "zoom": form.photo_crop_zoom.data,
                    },
                )
                new_photo_key = generate_profile_photo_key()
                try:
                    storage.save(new_photo_key, processed_photo)
                except OSError:
                    raise ProfilePhotoError("We couldn't save that photo right now. Please try again.") from None
            if profile_record is None:
                # The unique user_id constraint is the final guard against duplicates.
                profile_record = Profile(user=g.user)
                db.session.add(profile_record)

            g.user.date_of_birth = form.date_of_birth.data
            profile_record.gender = form.gender.data
            profile_record.gender_description = (
                form.gender_description.data if form.gender.data == "self_described" else None
            )
            profile_record.bio = form.bio.data or None
            profile_record.home_country_code = form.home_country_code.data
            profile_record.home_city = form.home_city.data
            profile_record.discovery_country_code = form.discovery_country_code.data
            profile_record.discovery_city = form.discovery_city.data
            profile_record.open_to_connections = form.open_to_connections.data
            if new_photo_key:
                profile_record.profile_photo_key = new_photo_key
            profile_record.languages = selected_records(Language, form.languages.data)
            profile_record.interests = selected_records(Interest, form.interests.data)
            profile_record.connection_intents = selected_records(ConnectionIntent, form.connection_intents.data)
            db.session.commit()
            if new_photo_key and old_photo_key and not storage.delete(old_photo_key):
                app.logger.warning("Old profile photo could not be removed: %s", old_photo_key)
            flash("Your profile has been saved.", "success")
            return redirect(url_for("profile"))
        except ProfilePhotoError as error:
            if new_photo_key:
                storage.delete(new_photo_key)
            form.profile_photo.errors = [*form.profile_photo.errors, str(error)]
        except SQLAlchemyError:
            db.session.rollback()
            if new_photo_key:
                storage.delete(new_photo_key)
            app.logger.exception("Profile update failed because of a database error.")
            flash("We couldn't save your profile right now. Please try again.", "error")

    grouped_interests = {}
    for identifier, label in form.interests.choices:
        interest = db.session.get(Interest, identifier)
        grouped_interests.setdefault(interest.category, []).append((identifier, label))
    return render_template(
        "profile_form.html",
        form=form,
        profile=profile_record,
        grouped_interests=grouped_interests,
        remove_photo_form=RemoveProfilePhotoForm(),
    )


@app.route("/profile/photo/remove", methods=["POST"])
@login_required
def remove_profile_photo():
    """Deliberately detach and delete the signed-in user's profile photo."""
    form = RemoveProfilePhotoForm()
    if not form.validate_on_submit():
        abort(400)
    profile_record = g.user.profile
    if profile_record is None or not profile_record.profile_photo_key:
        flash("There is no profile photo to remove.", "info")
        return redirect(url_for("edit_profile"))

    key = profile_record.profile_photo_key
    try:
        profile_record.profile_photo_key = None
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Profile photo removal failed because of a database error.")
        flash("We couldn't remove your photo right now. Please try again.", "error")
        return redirect(url_for("edit_profile"))

    if not profile_photo_storage().delete(key):
        app.logger.warning("Detached profile photo could not be deleted: %s", key)
    flash("Your profile photo has been removed.", "success")
    return redirect(url_for("edit_profile"))


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    form = LogoutForm()
    if form.validate_on_submit():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("login"))

    return redirect(url_for("dashboard"))


@app.cli.command("seed-profile-data")
def seed_profile_data():
    """Idempotently populate profile catalogues; never runs during app startup."""
    for name, code in LANGUAGES:
        existing = db.session.scalar(db.select(Language).where(Language.code == code))
        if existing is not None:
            # Normalize labels in place so profile-language associations retain
            # the same row IDs. Never delete catalogue records during seeding.
            conflicting_name = db.session.scalar(
                db.select(Language).where(Language.name == name, Language.id != existing.id)
            )
            if conflicting_name is None:
                existing.name = name
            continue

        # A legacy row with the desired display name is upgraded in place rather
        # than duplicated, preserving any profiles already associated with it.
        existing = db.session.scalar(db.select(Language).where(Language.name == name))
        if existing is not None:
            existing.code = code
        else:
            db.session.add(Language(name=name, code=code))
    for category, names in INTERESTS.items():
        for name in names:
            slug = slugify_interest(name)
            if db.session.scalar(db.select(Interest).where(Interest.slug == slug)) is None:
                db.session.add(Interest(name=name, slug=slug, category=category))
    for name, slug in CONNECTION_INTENTS:
        if db.session.scalar(db.select(ConnectionIntent).where(ConnectionIntent.slug == slug)) is None:
            db.session.add(ConnectionIntent(name=name, slug=slug))
    db.session.commit()
    print("Profile data is ready.")


if __name__ == "__main__":
    app.run(debug=True)
