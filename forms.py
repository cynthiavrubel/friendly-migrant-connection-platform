"""WTForms definitions for Friendly authentication flows."""

import re

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError


def strip_whitespace(value: str | None) -> str | None:
    """Normalize surrounding whitespace before validation."""
    return value.strip() if value else value


def normalize_email(value: str | None) -> str | None:
    """Normalize email addresses for consistent lookup and storage."""
    return value.strip().lower() if value else value


class RegistrationForm(FlaskForm):
    """Validate the information required to create a Friendly account."""

    first_name = StringField("First name", filters=[strip_whitespace], validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField("Last name", filters=[strip_whitespace], validators=[DataRequired(), Length(min=2, max=50)])
    email = StringField("Email address", filters=[normalize_email], validators=[DataRequired(), Email(), Length(max=255)])
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
