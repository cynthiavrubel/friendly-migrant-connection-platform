"""WTForms definitions for Friendly authentication flows."""

import re
from datetime import date

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import BooleanField, DateField, HiddenField, PasswordField, SelectField, SelectMultipleField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, ValidationError

from profile_data import GENDER_CHOICES, country_choices


def strip_whitespace(value: str | None) -> str | None:
    """Normalize surrounding whitespace before validation."""
    return value.strip() if value else value


def normalize_email(value: str | None) -> str | None:
    """Normalize email addresses for consistent lookup and storage."""
    return value.strip().lower() if value else value


def validate_adult_date_of_birth(_form, field):
    """Enforce Friendly's 18+ policy using the submitted calendar date."""
    if field.data is None:
        raise ValidationError("Please enter your date of birth.")
    today = date.today()
    if field.data > today:
        raise ValidationError("Date of birth cannot be in the future.")
    age = today.year - field.data.year - ((today.month, today.day) < (field.data.month, field.data.day))
    if age < 18:
        raise ValidationError("You must be at least 18 years old to join Friendly.")


class RegistrationForm(FlaskForm):
    """Validate the information required to create a Friendly account."""

    first_name = StringField("First name", filters=[strip_whitespace], validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField("Last name", filters=[strip_whitespace], validators=[DataRequired(), Length(min=2, max=50)])
    email = StringField("Email address", filters=[normalize_email], validators=[DataRequired(), Email(), Length(max=255)])
    date_of_birth = DateField("Date of birth", validators=[DataRequired(), validate_adult_date_of_birth])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password", message="Passwords must match.")])
    submit = SubmitField("Create Account")

    def validate_password(self, field: PasswordField) -> None:
        """Require a practical baseline of password complexity."""
        password = field.data or ""
        missing_requirements = []
        if not re.search(r"[A-Z]", password):
            missing_requirements.append("one uppercase letter")
        if not re.search(r"[a-z]", password):
            missing_requirements.append("one lowercase letter")
        if not re.search(r"\d", password):
            missing_requirements.append("one number")
        if missing_requirements:
            raise ValidationError(f"Password must include at least {', '.join(missing_requirements)}.")


class LoginForm(FlaskForm):
    """Validate credentials submitted through the login page."""

    email = StringField(
        "Email address",
        filters=[normalize_email],
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember me")
    submit = SubmitField("Log In")


class LogoutForm(FlaskForm):
    """Provide CSRF protection for the logout action."""

    submit = SubmitField("Log Out")


class RemoveProfilePhotoForm(FlaskForm):
    """Provide CSRF protection for deliberate profile-photo removal."""

    submit = SubmitField("Remove photo")


class ConnectionRequestForm(FlaskForm):
    """Validate an optional, plain-text introduction for a connection request."""

    introduction = TextAreaField(
        "Optional introduction",
        filters=[strip_whitespace],
        validators=[Optional(), Length(max=300)],
    )
    submit = SubmitField("Send request")


class ConnectionActionForm(FlaskForm):
    """Provide CSRF protection for connection state transitions."""

    submit = SubmitField("Continue")


class ProfileForm(FlaskForm):
    """Validate creation and editing of a complete Friendly profile."""

    date_of_birth = DateField("Date of birth", validators=[DataRequired(), validate_adult_date_of_birth])
    gender = SelectField("Gender", choices=[("", "Choose an option"), *GENDER_CHOICES], validators=[DataRequired()])
    gender_description = StringField("Describe your gender", filters=[strip_whitespace], validators=[Optional(), Length(max=50)])
    bio = TextAreaField("Bio", filters=[strip_whitespace], validators=[Optional(), Length(max=500)])
    profile_photo = FileField("Profile photo")
    photo_crop_x = HiddenField(default="0.5")
    photo_crop_y = HiddenField(default="0.5")
    photo_crop_zoom = HiddenField(default="1")
    home_country_code = SelectField("Home country", choices=[], validators=[DataRequired()])
    home_city = StringField("Home city", filters=[strip_whitespace], validators=[DataRequired(), Length(min=2, max=100)])
    discovery_country_code = SelectField("Discovery country", choices=[], validators=[DataRequired()])
    discovery_city = StringField("Discovery city", filters=[strip_whitespace], validators=[DataRequired(), Length(min=2, max=100)])
    languages = SelectMultipleField("Languages", choices=[], coerce=int)
    interests = SelectMultipleField("Interests", choices=[], coerce=int)
    connection_intents = SelectMultipleField("Connection intentions", choices=[], coerce=int)
    open_to_connections = BooleanField("I am open to new connections", default=True)
    submit = SubmitField("Save profile")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.home_country_code.choices = [("", "Choose a country"), *country_choices()]
        self.discovery_country_code.choices = [("", "Choose a country"), *country_choices()]

    def validate_gender_description(self, field):
        if self.gender.data == "self_described" and not field.data:
            raise ValidationError("Please tell us how you describe your gender.")

    def validate_languages(self, field):
        if len(field.data or []) < 1:
            raise ValidationError("Choose at least one language.")

    def validate_interests(self, field):
        count = len(field.data or [])
        if count < 3 or count > 12:
            raise ValidationError("Choose between 3 and 12 interests.")

    def validate_connection_intents(self, field):
        if len(field.data or []) < 1:
            raise ValidationError("Choose at least one connection intention.")
