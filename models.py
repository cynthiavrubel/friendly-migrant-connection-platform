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


class ConnectionRequest(db.Model):
    """One directional request/state row for an unordered pair of members."""

    __tablename__ = "connection_requests"
    __table_args__ = (
        db.CheckConstraint("sender_id <> recipient_id", name="ck_connection_requests_distinct_users"),
        db.CheckConstraint("pair_low_id < pair_high_id", name="ck_connection_requests_ordered_pair"),
        db.CheckConstraint(
            "(sender_id = pair_low_id AND recipient_id = pair_high_id) OR "
            "(sender_id = pair_high_id AND recipient_id = pair_low_id)",
            name="ck_connection_requests_pair_members",
        ),
        db.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined')",
            name="ck_connection_requests_status",
        ),
        db.UniqueConstraint("pair_low_id", "pair_high_id", name="uq_connection_requests_pair"),
        db.Index("ix_connection_requests_recipient_status", "recipient_id", "status"),
        db.Index("ix_connection_requests_sender_status", "sender_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Canonical pair IDs enforce one state machine regardless of direction.
    pair_low_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    pair_high_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="pending")
    introductory_message = db.Column(db.String(300))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    responded_at = db.Column(db.DateTime(timezone=True))

    sender = db.relationship("User", foreign_keys=[sender_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])


class Conversation(db.Model):
    """The single durable private conversation for an unordered member pair."""

    __tablename__ = "conversations"
    __table_args__ = (
        db.CheckConstraint("user_low_id < user_high_id", name="ck_conversations_ordered_pair"),
        db.UniqueConstraint("user_low_id", "user_high_id", name="uq_conversations_pair"),
        db.Index("ix_conversations_low_activity", "user_low_id", "last_activity_at"),
        db.Index("ix_conversations_high_activity", "user_high_id", "last_activity_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_low_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user_high_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_activity_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    user_low = db.relationship("User", foreign_keys=[user_low_id])
    user_high = db.relationship("User", foreign_keys=[user_high_id])
    messages = db.relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Message(db.Model):
    """A plain-text message whose sender is always inferred from the session."""

    __tablename__ = "messages"
    __table_args__ = (
        db.Index("ix_messages_conversation_created", "conversation_id", "created_at", "id"),
        db.Index("ix_messages_conversation_unread", "conversation_id", "read_at", "sender_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body = db.Column(db.String(2000), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    read_at = db.Column(db.DateTime(timezone=True))

    conversation = db.relationship("Conversation", back_populates="messages")
    sender = db.relationship("User", foreign_keys=[sender_id])


class CommunityPlan(db.Model):
    """A public local activity hosted by one Friendly member."""

    __tablename__ = "community_plans"
    __table_args__ = (
        db.CheckConstraint("capacity >= 2 AND capacity <= 20", name="ck_community_plans_capacity"),
        db.CheckConstraint("status IN ('active', 'cancelled')", name="ck_community_plans_status"),
        db.Index("ix_plans_location_status_start", "country_code", "city_normalized", "status", "starts_at"),
        db.Index("ix_plans_creator_start", "creator_id", "starts_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(40), nullable=False)
    description = db.Column(db.String(1200), nullable=False)
    country_code = db.Column(db.String(2), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    city_normalized = db.Column(db.String(100), nullable=False)
    starts_at = db.Column(db.DateTime(timezone=True), nullable=False)
    # UTC remains authoritative; this IANA key preserves the host's civil time.
    timezone = db.Column(db.String(64), nullable=False, default="UTC")
    meeting_place_text = db.Column(db.String(200))
    capacity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    cancelled_at = db.Column(db.DateTime(timezone=True))

    creator = db.relationship("User", foreign_keys=[creator_id])
    participants = db.relationship("PlanParticipant", back_populates="plan", cascade="all, delete-orphan", passive_deletes=True)


class PlanParticipant(db.Model):
    """Normalized membership in a community plan, including its host."""

    __tablename__ = "plan_participants"
    __table_args__ = (db.Index("ix_plan_participants_user_joined", "user_id", "joined_at"),)

    plan_id = db.Column(db.Integer, db.ForeignKey("community_plans.id", ondelete="CASCADE"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    joined_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    plan = db.relationship("CommunityPlan", back_populates="participants")
    user = db.relationship("User", foreign_keys=[user_id])


class Notification(db.Model):
    """A derived in-app activity record; domain models remain authoritative."""

    __tablename__ = "notifications"
    __table_args__ = (
        db.CheckConstraint(
            "type IN ('connection_request_received', 'connection_request_accepted', 'new_message', "
            "'plan_participant_joined', 'plan_participant_left', 'plan_participant_removed', 'plan_cancelled')",
            name="ck_notifications_type",
        ),
        db.Index("ix_notifications_user_read", "user_id", "read_at"),
        db.Index("ix_notifications_user_created", "user_id", "created_at"),
        db.Index(
            "ix_notifications_coalesce",
            "user_id",
            "type",
            "related_entity_type",
            "related_entity_id",
            "read_at",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    type = db.Column(db.String(40), nullable=False)
    related_entity_type = db.Column(db.String(32))
    related_entity_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    read_at = db.Column(db.DateTime(timezone=True))

    user = db.relationship("User", foreign_keys=[user_id])
    actor = db.relationship("User", foreign_keys=[actor_id])


class UserBlock(db.Model):
    """A directional safety choice that restricts interaction in both directions."""

    __tablename__ = "user_blocks"
    __table_args__ = (
        db.CheckConstraint("blocker_id <> blocked_id", name="ck_user_blocks_distinct_users"),
        db.UniqueConstraint("blocker_id", "blocked_id", name="uq_user_blocks_direction"),
        db.Index("ix_user_blocks_blocked_blocker", "blocked_id", "blocker_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    blocker = db.relationship("User", foreign_keys=[blocker_id])
    blocked = db.relationship("User", foreign_keys=[blocked_id])


class UserReport(db.Model):
    """A private, non-punitive moderation record submitted by a member."""

    __tablename__ = "user_reports"
    __table_args__ = (
        db.CheckConstraint(
            "reason IN ('harassment', 'hate_or_abuse', 'sexual_or_inappropriate', "
            "'spam_or_scam', 'impersonation', 'unsafe_behavior', 'other')",
            name="ck_user_reports_reason",
        ),
        db.CheckConstraint("status IN ('open')", name="ck_user_reports_status"),
        db.Index("ix_user_reports_reporter_created", "reporter_id", "created_at"),
        db.Index("ix_user_reports_reported_created", "reported_user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    # Nullable SET NULL keeps moderation history if account deletion is added later.
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reported_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason = db.Column(db.String(40), nullable=False)
    details = db.Column(db.String(2000))
    status = db.Column(db.String(16), nullable=False, default="open")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    reporter = db.relationship("User", foreign_keys=[reporter_id])
    reported_user = db.relationship("User", foreign_keys=[reported_user_id])
