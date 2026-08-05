from datetime import datetime
from functools import wraps
from urllib.parse import unquote, urlsplit

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import SQLAlchemyError

from config import DevelopmentConfig
from forms import LoginForm, LogoutForm, RegistrationForm
from models import User, db

app = Flask(__name__)
app.config.from_object(DevelopmentConfig)

# Extensions are initialized without creating tables; schema changes use migrations.
db.init_app(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)


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
    return {"current_year": datetime.now().year, "current_user": g.user}


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
                user = User(first_name=form.first_name.data.strip(), last_name=form.last_name.data.strip(), email=email)
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
    return render_template("dashboard.html", logout_form=LogoutForm())


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    form = LogoutForm()
    if form.validate_on_submit():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("login"))

    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
