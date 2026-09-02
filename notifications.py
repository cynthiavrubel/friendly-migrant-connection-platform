"""Creation, coalescing, presentation, and read state for in-app activity."""

from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil

from flask import url_for
from sqlalchemy.orm import joinedload

from models import CommunityPlan, Conversation, Notification, User, db


NOTIFICATION_TYPES = {
    "connection_request_received",
    "connection_request_accepted",
    "new_message",
    "plan_participant_joined",
    "plan_participant_left",
    "plan_participant_removed",
    "plan_cancelled",
}
PER_PAGE = 20


class NotificationError(Exception):
    """A privacy-safe notification lookup or mutation failure."""


@dataclass(frozen=True)
class NotificationView:
    notification: Notification
    text: str
    destination: str
    plan: CommunityPlan | None = None


@dataclass(frozen=True)
class NotificationPage:
    items: list[NotificationView]
    page: int
    pages: int
    total: int

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages


def utc_now():
    return datetime.now(timezone.utc)


def create_notification(session, recipient_id, notification_type, *, actor_id=None, entity_type=None, entity_id=None, now=None):
    """Create only controlled, non-self activity inside the caller's transaction."""
    if notification_type not in NOTIFICATION_TYPES:
        raise ValueError("Unsupported notification type")
    if actor_id is not None and recipient_id == actor_id:
        return None
    notification = Notification(
        user_id=recipient_id,
        actor_id=actor_id,
        type=notification_type,
        related_entity_type=entity_type,
        related_entity_id=entity_id,
        created_at=now or utc_now(),
    )
    session.add(notification)
    return notification


def notify_connection_request(session, relationship, *, now=None):
    return create_notification(session, relationship.recipient_id, "connection_request_received", actor_id=relationship.sender_id, entity_type="connection", entity_id=relationship.id, now=now)


def notify_connection_accepted(session, relationship, *, now=None):
    return create_notification(session, relationship.sender_id, "connection_request_accepted", actor_id=relationship.recipient_id, entity_type="connection", entity_id=relationship.id, now=now)


def notify_new_message(session, message, conversation, recipient_id, *, now=None):
    """Coalesce unread message activity per recipient and conversation."""
    now = now or utc_now()
    existing = session.scalar(
        db.select(Notification).where(
            Notification.user_id == recipient_id,
            Notification.type == "new_message",
            Notification.related_entity_type == "conversation",
            Notification.related_entity_id == conversation.id,
            Notification.read_at.is_(None),
        ).with_for_update()
    )
    if existing is not None:
        existing.actor_id = message.sender_id
        existing.created_at = now
        return existing
    return create_notification(session, recipient_id, "new_message", actor_id=message.sender_id, entity_type="conversation", entity_id=conversation.id, now=now)


def notify_plan_join(session, plan, actor_id, *, now=None):
    return create_notification(session, plan.creator_id, "plan_participant_joined", actor_id=actor_id, entity_type="plan", entity_id=plan.id, now=now)


def notify_plan_leave(session, plan, actor_id, *, now=None):
    return create_notification(session, plan.creator_id, "plan_participant_left", actor_id=actor_id, entity_type="plan", entity_id=plan.id, now=now)


def notify_plan_removed(session, plan, participant_id, actor_id, *, now=None):
    return create_notification(session, participant_id, "plan_participant_removed", actor_id=actor_id, entity_type="plan", entity_id=plan.id, now=now)


def notify_plan_cancelled(session, plan, actor_id, *, now=None):
    return [
        create_notification(session, participant.user_id, "plan_cancelled", actor_id=actor_id, entity_type="plan", entity_id=plan.id, now=now)
        for participant in plan.participants
        if participant.user_id != actor_id
    ]


def unread_notification_count(session, user_id):
    return session.scalar(db.select(db.func.count(Notification.id)).where(Notification.user_id == user_id, Notification.read_at.is_(None))) or 0


def owned_notification(session, notification_id, user_id):
    notification = session.scalar(db.select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id))
    if notification is None:
        raise NotificationError()
    return notification


def mark_read(session, notification_id, user_id, *, now=None):
    notification = owned_notification(session, notification_id, user_id)
    if notification.read_at is None:
        notification.read_at = now or utc_now()
    return notification


def mark_all_read(session, user_id, *, now=None):
    return session.execute(
        db.update(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None)).values(read_at=now or utc_now())
    ).rowcount


def _text(notification, plan):
    actor = notification.actor.first_name if notification.actor is not None else "A user"
    plan_title = plan.title if plan is not None else "a community plan"
    return {
        "connection_request_received": f"{actor} sent you a connection request.",
        "connection_request_accepted": f"{actor} accepted your connection request.",
        "new_message": f"{actor} sent you a message.",
        "plan_participant_joined": f"{actor} joined your plan {plan_title}.",
        "plan_participant_left": f"{actor} left your plan {plan_title}.",
        "plan_participant_removed": f"You were removed from {plan_title}.",
        "plan_cancelled": f"{plan_title} was cancelled by {actor}.",
    }[notification.type]


def _destination(notification, existing_plan_ids, existing_conversation_ids):
    if notification.type == "connection_request_received":
        return url_for("connections", tab="received")
    if notification.type == "connection_request_accepted":
        return url_for("person_profile", user_id=notification.actor_id) if notification.actor_id else url_for("connections")
    if notification.type == "new_message":
        if notification.related_entity_id in existing_conversation_ids:
            return url_for("conversation", conversation_id=notification.related_entity_id)
        return url_for("messages")
    if notification.related_entity_id in existing_plan_ids:
        return url_for("community_plan", plan_id=notification.related_entity_id)
    return url_for("my_community_plans")


def notification_page(session, user_id, requested_page=1):
    total = session.scalar(db.select(db.func.count(Notification.id)).where(Notification.user_id == user_id)) or 0
    pages = max(1, ceil(total / PER_PAGE))
    page = min(max(1, requested_page), pages)
    notifications = list(session.scalars(
        db.select(Notification)
        .options(joinedload(Notification.actor).joinedload(User.profile))
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * PER_PAGE)
        .limit(PER_PAGE)
    ).unique())
    plan_ids = {item.related_entity_id for item in notifications if item.related_entity_type == "plan" and item.related_entity_id}
    plans = {plan.id: plan for plan in session.scalars(db.select(CommunityPlan).where(CommunityPlan.id.in_(plan_ids)))} if plan_ids else {}
    conversation_ids = {item.related_entity_id for item in notifications if item.related_entity_type == "conversation" and item.related_entity_id}
    existing_conversations = set(session.scalars(
        db.select(Conversation.id).where(
            Conversation.id.in_(conversation_ids),
            db.or_(Conversation.user_low_id == user_id, Conversation.user_high_id == user_id),
        )
    )) if conversation_ids else set()
    items = [NotificationView(item, _text(item, plans.get(item.related_entity_id)), _destination(item, set(plans), existing_conversations), plans.get(item.related_entity_id)) for item in notifications]
    return NotificationPage(items, page, pages, total)


def destination_for(session, notification, user_id):
    plan_ids = set()
    conversation_ids = set()
    if notification.related_entity_type == "plan" and notification.related_entity_id and session.get(CommunityPlan, notification.related_entity_id):
        plan_ids.add(notification.related_entity_id)
    if notification.related_entity_type == "conversation" and notification.related_entity_id:
        conversation = session.scalar(db.select(Conversation.id).where(Conversation.id == notification.related_entity_id, db.or_(Conversation.user_low_id == user_id, Conversation.user_high_id == user_id)))
        if conversation:
            conversation_ids.add(conversation)
    return _destination(notification, plan_ids, conversation_ids)


def format_notification_time(value, now=None):
    now = now or utc_now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    delta = now - value
    if delta.total_seconds() < 60:
        return "Just now"
    if delta.total_seconds() < 3600:
        return f"{int(delta.total_seconds() // 60)}m ago"
    if delta.total_seconds() < 86400:
        return f"{int(delta.total_seconds() // 3600)}h ago"
    return value.strftime("%d %b %Y")
