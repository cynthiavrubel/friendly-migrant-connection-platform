"""Central blocking, interaction restrictions, cleanup, and private reporting."""

from datetime import datetime, timezone

from sqlalchemy import case, delete, or_, select
from sqlalchemy.orm import joinedload

from models import CommunityPlan, ConnectionRequest, PlanParticipant, User, UserBlock, UserReport


REPORT_REASONS = (
    ("harassment", "Harassment"),
    ("hate_or_abuse", "Hate or abuse"),
    ("sexual_or_inappropriate", "Sexual or inappropriate behaviour"),
    ("spam_or_scam", "Spam or scam"),
    ("impersonation", "Impersonation"),
    ("unsafe_behavior", "Unsafe behaviour"),
    ("other", "Something else"),
)
REPORT_REASON_KEYS = {value for value, _ in REPORT_REASONS}


class SafetyError(Exception):
    """A privacy-safe safety action error."""

    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.message = message
        self.code = code


def utc_now():
    return datetime.now(timezone.utc)


def blocked_user_ids_select(user_id):
    """Return one SQL expression containing both inbound and outbound blocks."""
    return select(
        case((UserBlock.blocker_id == user_id, UserBlock.blocked_id), else_=UserBlock.blocker_id)
    ).where(or_(UserBlock.blocker_id == user_id, UserBlock.blocked_id == user_id))


def is_blocked_pair(session, first_id, second_id):
    if first_id == second_id:
        return False
    return session.scalar(
        select(UserBlock.id).where(
            or_(
                (UserBlock.blocker_id == first_id) & (UserBlock.blocked_id == second_id),
                (UserBlock.blocker_id == second_id) & (UserBlock.blocked_id == first_id),
            )
        ).limit(1)
    ) is not None


def block_user(session, blocker_id, blocked_id, *, now=None):
    """Create one block and quietly clean up pair interactions in one transaction."""
    if blocker_id == blocked_id:
        raise SafetyError("You cannot block yourself.", "self")
    if session.get(User, blocked_id) is None:
        raise SafetyError("That member could not be found.", "not_found")
    existing = session.scalar(
        select(UserBlock).where(UserBlock.blocker_id == blocker_id, UserBlock.blocked_id == blocked_id).with_for_update()
    )
    if existing is None:
        existing = UserBlock(blocker_id=blocker_id, blocked_id=blocked_id, created_at=now or utc_now())
        session.add(existing)
        session.flush()

    low_id, high_id = sorted((blocker_id, blocked_id))
    session.execute(delete(ConnectionRequest).where(ConnectionRequest.pair_low_id == low_id, ConnectionRequest.pair_high_id == high_id))

    instant = now or utc_now()
    affected_plan_ids = select(CommunityPlan.id).where(
        CommunityPlan.status == "active",
        CommunityPlan.starts_at > instant,
        CommunityPlan.creator_id.in_((blocker_id, blocked_id)),
    )
    session.execute(
        delete(PlanParticipant).where(
            PlanParticipant.plan_id.in_(affected_plan_ids),
            or_(
                (PlanParticipant.user_id == blocked_id)
                & PlanParticipant.plan_id.in_(select(CommunityPlan.id).where(CommunityPlan.creator_id == blocker_id)),
                (PlanParticipant.user_id == blocker_id)
                & PlanParticipant.plan_id.in_(select(CommunityPlan.id).where(CommunityPlan.creator_id == blocked_id)),
            ),
        )
    )
    session.flush()
    return existing


def unblock_user(session, blocker_id, blocked_id):
    if blocker_id == blocked_id:
        raise SafetyError("That block could not be found.", "not_found")
    block = session.scalar(
        select(UserBlock).where(UserBlock.blocker_id == blocker_id, UserBlock.blocked_id == blocked_id).with_for_update()
    )
    if block is not None:
        session.delete(block)
        session.flush()
    return block


def blocked_users(session, blocker_id):
    return list(session.scalars(
        select(UserBlock)
        .where(UserBlock.blocker_id == blocker_id)
        .options(joinedload(UserBlock.blocked).joinedload(User.profile))
        .order_by(UserBlock.created_at.desc(), UserBlock.id.desc())
    ).unique())


def report_user(session, reporter_id, reported_id, reason, details=None, *, now=None):
    if reporter_id == reported_id:
        raise SafetyError("You cannot report yourself.", "self")
    if session.get(User, reported_id) is None:
        raise SafetyError("That member could not be found.", "not_found")
    if reason not in REPORT_REASON_KEYS:
        raise SafetyError("Choose a valid report reason.", "reason")
    normalized = (details or "").strip() or None
    if len(normalized or "") > 2000:
        raise SafetyError("Additional details must be 2,000 characters or fewer.", "details")
    report = UserReport(reporter_id=reporter_id, reported_user_id=reported_id, reason=reason, details=normalized, status="open", created_at=now or utc_now())
    session.add(report)
    session.flush()
    return report
