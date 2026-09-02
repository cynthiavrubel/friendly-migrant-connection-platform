"""Business rules and efficient queries for Friendly Community Plans."""

from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from models import CommunityPlan, PlanParticipant, Profile, User, db
from safety import is_blocked_pair
from timezones import TimezoneError, local_to_utc, normalize_utc


PLAN_CATEGORIES = (
    ("coffee-food", "Coffee & food"),
    ("walks-outdoors", "Walks & outdoors"),
    ("sports-fitness", "Sports & fitness"),
    ("cinema-entertainment", "Cinema & entertainment"),
    ("culture-museums", "Culture & museums"),
    ("study-language", "Study & language exchange"),
    ("games-social", "Games & social"),
    ("travel-exploring", "Travel & exploring"),
    ("other", "Other"),
)
CATEGORY_LABELS = dict(PLAN_CATEGORIES)
PLANS_PER_PAGE = 12


class PlanError(Exception):
    """A safe product-level plan error suitable for member feedback."""

    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class PlanPage:
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


def aware_utc(value):
    """Backward-compatible alias for centralized database UTC normalization."""
    return normalize_utc(value)


def normalize_city(value):
    return " ".join((value or "").strip().split()).casefold()


def plan_is_past(plan, now=None):
    return aware_utc(plan.starts_at) <= (now or utc_now())


def plan_state(plan, participant_count=None, now=None):
    if plan.status == "cancelled":
        return "cancelled"
    if plan_is_past(plan, now):
        return "past"
    if participant_count is not None and participant_count >= plan.capacity:
        return "full"
    return "available"


def validate_plan_values(data, *, now=None):
    if data["category"] not in CATEGORY_LABELS:
        raise PlanError("Choose a valid plan category.", "category")
    if not 2 <= data["capacity"] <= 20:
        raise PlanError("Capacity must be between 2 and 20 people.", "capacity")
    timezone_key = data.get("timezone") or "UTC"
    try:
        starts_at = local_to_utc(data["starts_at"], timezone_key)
    except TimezoneError as error:
        field = "timezone" if error.code == "invalid_timezone" else "starts_at"
        raise PlanError(error.message, field) from error
    if starts_at is None or starts_at <= (now or utc_now()):
        raise PlanError("Choose a future date and time.", "starts_at")
    if not normalize_city(data["city"]):
        raise PlanError("Enter a city for this plan.", "city")
    return starts_at, timezone_key


def create_plan(session, creator, data, *, now=None):
    now = now or utc_now()
    starts_at, timezone_key = validate_plan_values(data, now=now)
    city = " ".join(data["city"].strip().split())
    plan = CommunityPlan(
        creator_id=creator.id,
        title=data["title"].strip(),
        category=data["category"],
        description=data["description"].strip(),
        country_code=data["country_code"],
        city=city,
        city_normalized=normalize_city(city),
        starts_at=starts_at,
        timezone=timezone_key,
        meeting_place_text=(data.get("meeting_place_text") or "").strip() or None,
        capacity=data["capacity"],
        status="active",
        created_at=now,
        updated_at=now,
    )
    session.add(plan)
    session.flush()
    session.add(PlanParticipant(plan_id=plan.id, user_id=creator.id, joined_at=now))
    session.flush()
    return plan


def _plan_query_options():
    return (
        joinedload(CommunityPlan.creator).joinedload(User.profile),
        selectinload(CommunityPlan.participants),
    )


def browse_plans(session, profile, requested_page=1, categories=None, *, now=None):
    now = now or utc_now()
    categories = set(categories or ()) & set(CATEGORY_LABELS)
    conditions = [
        CommunityPlan.status == "active",
        CommunityPlan.starts_at > now,
        CommunityPlan.country_code == profile.discovery_country_code,
        CommunityPlan.city_normalized == normalize_city(profile.discovery_city),
    ]
    if categories:
        conditions.append(CommunityPlan.category.in_(categories))
    total = session.scalar(db.select(db.func.count(CommunityPlan.id)).where(*conditions)) or 0
    pages = max(1, ceil(total / PLANS_PER_PAGE))
    page = min(max(1, requested_page), pages)
    items = list(session.scalars(
        db.select(CommunityPlan)
        .options(*_plan_query_options())
        .where(*conditions)
        .order_by(CommunityPlan.starts_at, CommunityPlan.id)
        .offset((page - 1) * PLANS_PER_PAGE)
        .limit(PLANS_PER_PAGE)
    ).unique())
    return PlanPage(items, page, pages, total)


def plan_details(session, plan_id, *, lock=False):
    statement = (
        db.select(CommunityPlan)
        .options(
            joinedload(CommunityPlan.creator).joinedload(User.profile),
            selectinload(CommunityPlan.participants).joinedload(PlanParticipant.user).joinedload(User.profile),
        )
        .where(CommunityPlan.id == plan_id)
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def participant_ids(plan):
    return {participant.user_id for participant in plan.participants}


def join_plan(session, plan_id, actor_id, *, now=None):
    """Lock the plan row so concurrent MySQL joins serialize before counting."""
    now = now or utc_now()
    plan = session.scalar(db.select(CommunityPlan).where(CommunityPlan.id == plan_id).with_for_update())
    if plan is None:
        raise PlanError("That plan could not be found.", "not_found")
    if plan.status != "active" or plan_is_past(plan, now):
        raise PlanError("This plan is no longer open for joining.", "read_only")
    if is_blocked_pair(session, actor_id, plan.creator_id):
        raise PlanError("This plan is not available for joining.", "blocked")
    exists = session.get(PlanParticipant, (plan.id, actor_id))
    if exists is not None:
        raise PlanError("You are already going to this plan.", "duplicate")
    count = session.scalar(db.select(db.func.count(PlanParticipant.user_id)).where(PlanParticipant.plan_id == plan.id)) or 0
    if count >= plan.capacity:
        raise PlanError("This plan is full.", "full")
    session.add(PlanParticipant(plan_id=plan.id, user_id=actor_id, joined_at=now))
    try:
        session.flush()
    except IntegrityError as error:
        raise PlanError("You are already going to this plan.", "duplicate") from error
    return plan


def leave_plan(session, plan_id, actor_id, *, now=None):
    plan = session.scalar(db.select(CommunityPlan).where(CommunityPlan.id == plan_id).with_for_update())
    if plan is None:
        raise PlanError("That plan could not be found.", "not_found")
    if plan.creator_id == actor_id:
        raise PlanError("Hosts cannot leave their own plan. Cancel it instead.", "host")
    if plan.status != "active" or plan_is_past(plan, now):
        raise PlanError("This plan is read-only.", "read_only")
    participant = session.get(PlanParticipant, (plan.id, actor_id))
    if participant is None:
        raise PlanError("You are not participating in this plan.", "not_participant")
    session.delete(participant)
    session.flush()
    return plan


def remove_participant(session, plan_id, participant_id, actor_id, *, now=None):
    plan = session.scalar(db.select(CommunityPlan).where(CommunityPlan.id == plan_id).with_for_update())
    if plan is None or plan.creator_id != actor_id:
        raise PlanError("That plan could not be found.", "not_found")
    if plan.status != "active" or plan_is_past(plan, now):
        raise PlanError("Participants cannot be changed on this plan.", "read_only")
    if participant_id == plan.creator_id:
        raise PlanError("The host cannot be removed.", "host")
    participant = session.get(PlanParticipant, (plan.id, participant_id))
    if participant is None:
        raise PlanError("That person is not participating in this plan.", "not_participant")
    session.delete(participant)
    session.flush()
    return plan


def edit_plan(session, plan_id, actor_id, data, *, now=None):
    now = now or utc_now()
    plan = session.scalar(db.select(CommunityPlan).where(CommunityPlan.id == plan_id).with_for_update())
    if plan is None or plan.creator_id != actor_id:
        raise PlanError("That plan could not be found.", "not_found")
    if plan.status != "active" or plan_is_past(plan, now):
        raise PlanError("Past or cancelled plans cannot be edited.", "read_only")
    starts_at, timezone_key = validate_plan_values(data, now=now)
    count = session.scalar(db.select(db.func.count(PlanParticipant.user_id)).where(PlanParticipant.plan_id == plan.id)) or 0
    if data["capacity"] < count:
        raise PlanError(f"Capacity cannot be lower than the {count} people already going.", "capacity")
    city = " ".join(data["city"].strip().split())
    plan.title = data["title"].strip()
    plan.category = data["category"]
    plan.description = data["description"].strip()
    plan.country_code = data["country_code"]
    plan.city = city
    plan.city_normalized = normalize_city(city)
    plan.starts_at = starts_at
    plan.timezone = timezone_key
    plan.meeting_place_text = (data.get("meeting_place_text") or "").strip() or None
    plan.capacity = data["capacity"]
    plan.updated_at = now
    session.flush()
    return plan


def cancel_plan(session, plan_id, actor_id, *, now=None):
    now = now or utc_now()
    plan = session.scalar(db.select(CommunityPlan).where(CommunityPlan.id == plan_id).with_for_update())
    if plan is None or plan.creator_id != actor_id:
        raise PlanError("That plan could not be found.", "not_found")
    if plan.status != "active" or plan_is_past(plan, now):
        raise PlanError("This plan can no longer be cancelled.", "read_only")
    plan.status = "cancelled"
    plan.cancelled_at = now
    plan.updated_at = now
    session.flush()
    return plan


def my_plans(session, actor_id, *, now=None):
    now = now or utc_now()
    rows = list(session.scalars(
        db.select(CommunityPlan)
        .join(PlanParticipant, PlanParticipant.plan_id == CommunityPlan.id)
        .options(*_plan_query_options())
        .where(PlanParticipant.user_id == actor_id)
        .order_by(CommunityPlan.starts_at.desc(), CommunityPlan.id.desc())
    ).unique())
    result = {"created_upcoming": [], "joined_upcoming": [], "created_history": [], "joined_history": []}
    for plan in rows:
        ownership = "created" if plan.creator_id == actor_id else "joined"
        timing = "history" if plan.status == "cancelled" or plan_is_past(plan, now) else "upcoming"
        result[f"{ownership}_{timing}"].append(plan)
    return result
