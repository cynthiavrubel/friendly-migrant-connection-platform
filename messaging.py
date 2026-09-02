"""Private messaging queries and permission rules for Friendly."""

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased, joinedload

from models import ConnectionRequest, Conversation, Message, User, db
from safety import blocked_user_ids_select, is_blocked_pair


INBOX_PAGE_SIZE = 20
MESSAGE_PAGE_SIZE = 50


class MessagingError(Exception):
    """A safe messaging error that routes may present to a member."""

    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class InboxItem:
    conversation: Conversation
    other_user: User
    last_message: Message | None
    unread: bool
    can_send: bool


@dataclass(frozen=True)
class Page:
    items: list
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


def pair_ids(first_id, second_id):
    if first_id == second_id:
        raise MessagingError("You cannot message yourself.", "self")
    return min(first_id, second_id), max(first_id, second_id)


def active_connection_between(session, first_id, second_id):
    low_id, high_id = pair_ids(first_id, second_id)
    return session.scalar(
        db.select(ConnectionRequest.id).where(
            ConnectionRequest.pair_low_id == low_id,
            ConnectionRequest.pair_high_id == high_id,
            ConnectionRequest.status == "accepted",
        )
    ) is not None


def conversation_between(session, first_id, second_id):
    low_id, high_id = pair_ids(first_id, second_id)
    return session.scalar(
        db.select(Conversation).where(
            Conversation.user_low_id == low_id,
            Conversation.user_high_id == high_id,
        )
    )


def start_conversation(session, actor_id, other_id):
    """Create once for an accepted pair, handling simultaneous first opens safely."""
    other = session.get(User, other_id)
    if other is None:
        raise MessagingError("That member could not be found.", "not_found")
    low_id, high_id = pair_ids(actor_id, other_id)
    if is_blocked_pair(session, actor_id, other_id):
        raise MessagingError("Messaging is unavailable with this member.", "blocked")
    if not active_connection_between(session, actor_id, other_id):
        raise MessagingError("You can only message active connections.", "not_connected")
    conversation = conversation_between(session, actor_id, other_id)
    if conversation is not None:
        return conversation
    try:
        with session.begin_nested():
            conversation = Conversation(user_low_id=low_id, user_high_id=high_id)
            session.add(conversation)
            session.flush()
    except IntegrityError:
        conversation = conversation_between(session, actor_id, other_id)
        if conversation is None:
            raise
    return conversation


def accessible_conversation(session, conversation_id, actor_id, *, lock=False):
    statement = (
        db.select(Conversation)
        .options(
            joinedload(Conversation.user_low).joinedload(User.profile),
            joinedload(Conversation.user_high).joinedload(User.profile),
        )
        .where(
            Conversation.id == conversation_id,
            db.or_(Conversation.user_low_id == actor_id, Conversation.user_high_id == actor_id),
        )
    )
    if lock:
        statement = statement.with_for_update()
    conversation = session.scalar(statement)
    if conversation is None:
        raise MessagingError("That conversation could not be found.", "not_found")
    return conversation


def other_participant(conversation, actor_id):
    return conversation.user_high if conversation.user_low_id == actor_id else conversation.user_low


def send_message(session, conversation_id, actor_id, body):
    # Serializing writes per conversation also makes unread notification
    # coalescing deterministic under concurrent sends on MySQL.
    conversation = accessible_conversation(session, conversation_id, actor_id, lock=True)
    other = other_participant(conversation, actor_id)
    if is_blocked_pair(session, actor_id, other.id):
        raise MessagingError("Messaging is unavailable for this conversation.", "blocked")
    if not active_connection_between(session, actor_id, other.id):
        raise MessagingError("This conversation is read-only because you are no longer connected.", "read_only")
    normalized = (body or "").strip()
    if not normalized:
        raise MessagingError("Write a message before sending.", "empty")
    if len(normalized) > 2000:
        raise MessagingError("Messages can be up to 2,000 characters.", "too_long")
    now = utc_now()
    message = Message(conversation_id=conversation.id, sender_id=actor_id, body=normalized, created_at=now)
    conversation.last_activity_at = now
    session.add(message)
    return message


def mark_conversation_read(session, conversation_id, actor_id):
    """Mark every received message read; the sender's own messages remain untouched."""
    return session.execute(
        db.update(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.sender_id != actor_id,
            Message.read_at.is_(None),
        )
        .values(read_at=utc_now())
    ).rowcount


def unread_conversation_count(session, actor_id):
    return session.scalar(
        db.select(db.func.count(db.distinct(Message.conversation_id)))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            db.or_(Conversation.user_low_id == actor_id, Conversation.user_high_id == actor_id),
            Message.sender_id != actor_id,
            Message.read_at.is_(None),
        )
    ) or 0


def _accepted_other_ids(session, actor_id, other_ids):
    if not other_ids:
        return set()
    rows = session.scalars(
        db.select(ConnectionRequest).where(
            ConnectionRequest.status == "accepted",
            db.or_(
                db.and_(ConnectionRequest.sender_id == actor_id, ConnectionRequest.recipient_id.in_(other_ids)),
                db.and_(ConnectionRequest.recipient_id == actor_id, ConnectionRequest.sender_id.in_(other_ids)),
            ),
        )
    )
    accepted = {
        row.recipient_id if row.sender_id == actor_id else row.sender_id
        for row in rows
    }
    blocked = set(session.scalars(blocked_user_ids_select(actor_id)))
    return accepted - blocked


def inbox_page(session, actor_id, requested_page=1):
    participant_filter = db.or_(Conversation.user_low_id == actor_id, Conversation.user_high_id == actor_id)
    total = session.scalar(db.select(db.func.count(Conversation.id)).where(participant_filter)) or 0
    pages = max(1, (total + INBOX_PAGE_SIZE - 1) // INBOX_PAGE_SIZE)
    page = min(max(1, requested_page), pages)
    conversations = list(session.scalars(
        db.select(Conversation)
        .options(
            joinedload(Conversation.user_low).joinedload(User.profile),
            joinedload(Conversation.user_high).joinedload(User.profile),
        )
        .where(participant_filter)
        .order_by(Conversation.last_activity_at.desc(), Conversation.id.desc())
        .offset((page - 1) * INBOX_PAGE_SIZE)
        .limit(INBOX_PAGE_SIZE)
    ).unique())
    conversation_ids = [item.id for item in conversations]
    last_messages = {}
    unread_ids = set()
    if conversation_ids:
        ranked_messages = db.select(
            Message,
            db.func.row_number().over(
                partition_by=Message.conversation_id,
                order_by=(Message.created_at.desc(), Message.id.desc()),
            ).label("position"),
        ).where(Message.conversation_id.in_(conversation_ids)).subquery()
        latest_message = aliased(Message, ranked_messages)
        for message in session.scalars(
            db.select(latest_message).where(ranked_messages.c.position == 1)
        ):
            last_messages[message.conversation_id] = message
        unread_ids = set(session.scalars(
            db.select(Message.conversation_id).distinct().where(
                Message.conversation_id.in_(conversation_ids),
                Message.sender_id != actor_id,
                Message.read_at.is_(None),
            )
        ))
    other_users = [other_participant(item, actor_id) for item in conversations]
    accepted_ids = _accepted_other_ids(session, actor_id, [user.id for user in other_users])
    items = [
        InboxItem(
            conversation=conversation,
            other_user=other_participant(conversation, actor_id),
            last_message=last_messages.get(conversation.id),
            unread=conversation.id in unread_ids,
            can_send=other_participant(conversation, actor_id).id in accepted_ids,
        )
        for conversation in conversations
    ]
    return Page(items, page, pages, total)


def message_page(session, conversation_id, requested_page=None):
    total = session.scalar(
        db.select(db.func.count(Message.id)).where(Message.conversation_id == conversation_id)
    ) or 0
    pages = max(1, (total + MESSAGE_PAGE_SIZE - 1) // MESSAGE_PAGE_SIZE)
    page = pages if requested_page is None else min(max(1, requested_page), pages)
    items = list(session.scalars(
        db.select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
        .offset((page - 1) * MESSAGE_PAGE_SIZE)
        .limit(MESSAGE_PAGE_SIZE)
    ))
    return Page(items, page, pages, total)


def message_preview(message, limit=90):
    if message is None:
        return "No messages yet"
    text = re.sub(r"\s+", " ", message.body).strip()
    return text if len(text) <= limit else f"{text[:limit - 1].rstrip()}…"


def format_message_time(value, now=None):
    if value is None:
        return ""
    now = now or utc_now()
    # SQLite may return naive values even for timezone-aware columns.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    difference = now.date() - value.astimezone(timezone.utc).date()
    if difference.days == 0:
        return value.strftime("%H:%M UTC")
    if difference.days == 1:
        return "Yesterday"
    return value.strftime("%d %b")
