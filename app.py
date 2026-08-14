from datetime import datetime
from functools import wraps
from urllib.parse import unquote, urlencode, urlsplit

from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import SQLAlchemyError

from config import DevelopmentConfig
from discovery import discover_profiles, parse_filters, public_profile
from forms import LoginForm, LogoutForm, ProfileForm, RegistrationForm, RemoveProfilePhotoForm
from models import ConnectionIntent, Interest, Language, Profile, User, db
from profile_data import CONNECTION_INTENTS, GENDER_CHOICES, INTERESTS, LANGUAGES, country_name, slugify_interest
from profile_photo_storage import PROFILE_PHOTO_KEY_PATTERN, build_profile_photo_storage
from profile_photos import ProfilePhotoError, generate_profile_photo_key, process_profile_photo

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
    return {"current_year": datetime.now().year, "current_user": g.user, "country_name": country_name}


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
    )


@app.route("/people/<int:user_id>")
@login_required
def person_profile(user_id):
    """Render only another member's deliberately public profile fields."""
    if user_id == g.user.id:
        return redirect(url_for("profile"))
    profile_record = public_profile(db.session, user_id)
    if profile_record is None:
        abort(404)
    return render_template(
        "person_profile.html",
        profile=profile_record,
        gender_labels=dict(GENDER_CHOICES),
    )


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
