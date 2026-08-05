from datetime import datetime

from flask import Flask, flash, redirect, render_template, url_for
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import SQLAlchemyError

from config import DevelopmentConfig
from forms import RegistrationForm
from models import User, db

app = Flask(__name__)
app.config.from_object(DevelopmentConfig)

# Extensions are initialized without creating tables; schema changes use migrations.
db.init_app(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)


@app.context_processor
def inject_current_year():
    """Make the current year available to shared page content."""
    return {"current_year": datetime.now().year}


@app.route("/")
def home():
    return render_template("home.html")


# Temporary route until login is implemented.
@app.route("/login")
def login():
    return "Log in is coming soon."


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


if __name__ == "__main__":
    app.run(debug=True)
