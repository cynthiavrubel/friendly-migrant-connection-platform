"""Connection state machine, eligibility, cooldowns, and presentation state."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload, selectinload

from models import ConnectionRequest, Profile, User


DECLINE_COOLDOWN = timedelta(days=30)


class ConnectionError(Exception):
    """A safe product-level connection error suitable for user feedback."""

    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class RelationshipState:
    key: str
    label: str
    relationship_id: int | None = None


def utc_now():
    return datetime.now(timezone.utc)


def pair_ids(first_user_id, second_user_id):
    if first_user_id == second_user_id:
        raise ConnectionError("You cannot connect with yourself.", "self")
    return tuple(sorted((first_user_id, second_user_id)))


def relationship_between(session, first_user_id, second_user_id, *, lock=False):
    low_id, high_id = pair_ids(first_user_id, second_user_id)
    statement = select(ConnectionRequest).where(
        ConnectionRequest.pair_low_id == low_id,
        ConnectionRequest.pair_high_id == high_id,
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def _aware(value):
    """Normalize timestamps returned without tzinfo by SQLite test databases."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def cooldown_active(relationship, sender_id, recipient_id, *, now=None):
    if not relationship or relationship.status != "declined":
        return False
    if relationship.sender_id != sender_id or relationship.recipient_id != recipient_id:
        return False
    responded_at = _aware(relationship.responded_at)
    return bool(responded_at and (now or utc_now()) < responded_at + DECLINE_COOLDOWN)


def relationship_state(viewer_id, other_user_id, relationship, *, now=None):
    if relationship is None:
        return RelationshipState("available", "Connect")
    if relationship.status == "accepted":
        return RelationshipState("connected", "Connected", relationship.id)
    if relationship.status == "pending":
        if relationship.sender_id == viewer_id:
            return RelationshipState("sent", "Request sent", relationship.id)
        return RelationshipState("received", "Respond to request", relationship.id)
    if cooldown_active(relationship, viewer_id, other_user_id, now=now):
        return RelationshipState("unavailable", "Connection unavailable for now", relationship.id)
    return RelationshipState("available", "Connect", relationship.id)


def states_for_users(session, viewer_id, other_user_ids):
    other_user_ids = set(other_user_ids)
    if not other_user_ids:
        return {}
    rows = list(
        session.scalars(
            select(ConnectionRequest).where(
                or_(
                    (ConnectionRequest.pair_low_id == viewer_id) & ConnectionRequest.pair_high_id.in_(other_user_ids),
                    (ConnectionRequest.pair_high_id == viewer_id) & ConnectionRequest.pair_low_id.in_(other_user_ids),
                )
            )
        )
    )
    by_other = {}
    for relationship in rows:
        other_id = relationship.pair_high_id if relationship.pair_low_id == viewer_id else relationship.pair_low_id
        by_other[other_id] = relationship_state(viewer_id, other_id, relationship)
    return {identifier: by_other.get(identifier, RelationshipState("available", "Connect")) for identifier in other_user_ids}


def send_request(session, sender, recipient_id, message=None, *, now=None):
    now = now or utc_now()
    if sender.profile is None or not sender.profile.is_complete:
        raise ConnectionError("Complete your profile before connecting with someone.", "incomplete_sender")
    recipient = session.get(User, recipient_id)
    if recipient is None:
        raise ConnectionError("That person is not available.", "recipient_unavailable")
    pair_ids(sender.id, recipient.id)
    if recipient.profile is None or not recipient.profile.is_complete or not recipient.profile.open_to_connections:
        raise ConnectionError("That person is not available for connections.", "recipient_unavailable")

    relationship = relationship_between(session, sender.id, recipient.id, lock=True)
    if relationship and relationship.status == "accepted":
        raise ConnectionError("You are already connected.", "connected")
    if relationship and relationship.status == "pending":
        if relationship.sender_id == sender.id:
            raise ConnectionError("Your connection request is already pending.", "pending")
        raise ConnectionError("You already have a request from this person.", "respond")
    if cooldown_active(relationship, sender.id, recipient.id, now=now):
        raise ConnectionError("Connection unavailable for now.", "cooldown")

    normalized_message = (message or "").strip() or None
    if len(normalized_message or "") > 300:
        raise ConnectionError("Your introduction must be 300 characters or fewer.", "message_too_long")
    low_id, high_id = pair_ids(sender.id, recipient.id)
    if relationship is None:
        relationship = ConnectionRequest(pair_low_id=low_id, pair_high_id=high_id)
        session.add(relationship)
    relationship.sender_id = sender.id
    relationship.recipient_id = recipient.id
    relationship.status = "pending"
    relationship.introductory_message = normalized_message
    relationship.created_at = now
    relationship.updated_at = now
    relationship.responded_at = None
    session.flush()
    return relationship


def accept_request(session, relationship_id, actor_id, *, now=None):
    relationship = session.scalar(select(ConnectionRequest).where(ConnectionRequest.id == relationship_id).with_for_update())
    if relationship is None or relationship.status != "pending" or relationship.recipient_id != actor_id:
        raise ConnectionError("That connection request is no longer available.", "unauthorized")
    relationship.status = "accepted"
    relationship.responded_at = now or utc_now()
    session.flush()
    return relationship


def decline_request(session, relationship_id, actor_id, *, now=None):
    relationship = session.scalar(select(ConnectionRequest).where(ConnectionRequest.id == relationship_id).with_for_update())
    if relationship is None or relationship.status != "pending" or relationship.recipient_id != actor_id:
        raise ConnectionError("That connection request is no longer available.", "unauthorized")
    relationship.status = "declined"
    relationship.responded_at = now or utc_now()
    session.flush()
    return relationship


def cancel_request(session, relationship_id, actor_id):
    relationship = session.scalar(select(ConnectionRequest).where(ConnectionRequest.id == relationship_id).with_for_update())
    if relationship is None or relationship.status != "pending" or relationship.sender_id != actor_id:
        raise ConnectionError("That connection request is no longer available.", "unauthorized")
    session.delete(relationship)
    session.flush()


def remove_connection(session, relationship_id, actor_id):
    relationship = session.scalar(select(ConnectionRequest).where(ConnectionRequest.id == relationship_id).with_for_update())
    if relationship is None or relationship.status != "accepted" or actor_id not in {relationship.sender_id, relationship.recipient_id}:
        raise ConnectionError("That connection is no longer available.", "unauthorized")
    session.delete(relationship)
    session.flush()


def connection_lists(session, user_id):
    """Load the three connection sections with profiles/catalogues in bounded queries."""
    options = (
        joinedload(ConnectionRequest.sender).joinedload(User.profile).selectinload(Profile.languages),
        joinedload(ConnectionRequest.sender).joinedload(User.profile).selectinload(Profile.interests),
        joinedload(ConnectionRequest.sender).joinedload(User.profile).selectinload(Profile.connection_intents),
        joinedload(ConnectionRequest.recipient).joinedload(User.profile).selectinload(Profile.languages),
        joinedload(ConnectionRequest.recipient).joinedload(User.profile).selectinload(Profile.interests),
        joinedload(ConnectionRequest.recipient).joinedload(User.profile).selectinload(Profile.connection_intents),
    )
    relationships = list(
        session.scalars(
            select(ConnectionRequest)
            .where(
                or_(ConnectionRequest.sender_id == user_id, ConnectionRequest.recipient_id == user_id),
                ConnectionRequest.status.in_(("pending", "accepted")),
            )
            .options(*options)
            .order_by(ConnectionRequest.updated_at.desc(), ConnectionRequest.id.desc())
        ).unique()
    )
    accepted, received, sent = [], [], []
    for relationship in relationships:
        if relationship.status == "accepted":
            accepted.append(relationship)
        elif relationship.recipient_id == user_id:
            received.append(relationship)
        else:
            sent.append(relationship)
    return {"connections": accepted, "received": received, "sent": sent}
