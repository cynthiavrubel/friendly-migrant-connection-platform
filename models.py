"""Database models for Friendly."""

from datetime import date, datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


# The unbound extension avoids importing the Flask app into the model module.
db = SQLAlchemy()

profile_languages = db.Table(
    "profile_languages",
    db.Column("profile_id", db.Integer, db.ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
    db.Column("language_id", db.Integer, db.ForeignKey("languages.id", ondelete="CASCADE"), primary_key=True),
)

profile_interests = db.Table(
    "profile_interests",
    db.Column("profile_id", db.Integer, db.ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
    db.Column("interest_id", db.Integer, db.ForeignKey("interests.id", ondelete="CASCADE"), primary_key=True),
)

profile_connection_intents = db.Table(
    "profile_connection_intents",
    db.Column("profile_id", db.Integer, db.ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
    db.Column("connection_intent_id", db.Integer, db.ForeignKey("connection_intents.id", ondelete="CASCADE"), primary_key=True),
)


class User(db.Model):
    """A Friendly member with securely hashed authentication credentials."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    # Nullable in the staged migration so existing accounts remain valid.
    date_of_birth = db.Column(db.Date, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    profile = db.relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")

    @property
    def age(self):
        """Return exact current age without persisting derived personal data."""
        if self.date_of_birth is None:
            return None
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    def set_password(self, password: str) -> None:
        """Hash and store a password; plaintext is never persisted."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Return whether a plaintext candidate matches the stored hash."""
        return check_password_hash(self.password_hash, password)


class Profile(db.Model):
    """A member's public connection profile and private location context."""

    __tablename__ = "profiles"
    __table_args__ = (db.Index("ux_profiles_profile_photo_key", "profile_photo_key", unique=True),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    gender = db.Column(db.String(24), nullable=False)
    gender_description = db.Column(db.String(50))
    bio = db.Column(db.String(500))
    # Storage-neutral object key; image bytes live in the configured storage backend.
    profile_photo_key = db.Column(db.String(255))
    home_country_code = db.Column(db.String(2), nullable=False)
    home_city = db.Column(db.String(100), nullable=False)
    discovery_country_code = db.Column(db.String(2), nullable=False)
    discovery_city = db.Column(db.String(100), nullable=False)
    open_to_connections = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", back_populates="profile")
    languages = db.relationship("Language", secondary=profile_languages, lazy="selectin")
    interests = db.relationship("Interest", secondary=profile_interests, lazy="selectin")
    connection_intents = db.relationship("ConnectionIntent", secondary=profile_connection_intents, lazy="selectin")

    @property
    def completion_items(self):
        """Return the single authoritative checklist used for profile gating."""
        return {
            "basic_identity": self.user.age is not None and self.user.age >= 18,
            "gender": bool(self.gender),
            "home_location": bool(self.home_country_code and self.home_city),
            "discovery_location": bool(self.discovery_country_code and self.discovery_city),
            "languages": len(self.languages) >= 1,
            "interests": 3 <= len(self.interests) <= 12,
            "connection_intentions": len(self.connection_intents) >= 1,
            "profile_photo": bool(self.profile_photo_key),
        }

    @property
    def completion_percentage(self):
        """Return an equal-weight integer completion percentage."""
        items = self.completion_items
        return round(sum(items.values()) * 100 / len(items))

    @property
    def is_complete(self):
        return all(self.completion_items.values())

    @property
    def missing_completion_items(self):
        labels = {
            "basic_identity": "a valid date of birth",
            "gender": "your gender selection",
            "home_location": "your home location",
            "discovery_location": "your discovery location",
            "languages": "at least one language",
            "interests": "between 3 and 12 interests",
            "connection_intentions": "at least one connection intention",
            "profile_photo": "a profile photo",
        }
        return [labels[key] for key, complete in self.completion_items.items() if not complete]


class Language(db.Model):
    __tablename__ = "languages"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    code = db.Column(db.String(12), unique=True, nullable=False)


class Interest(db.Model):
    __tablename__ = "interests"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    category = db.Column(db.String(40), nullable=False, index=True)


class ConnectionIntent(db.Model):
    __tablename__ = "connection_intents"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False)
