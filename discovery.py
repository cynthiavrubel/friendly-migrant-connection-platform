"""Transparent, deterministic people-discovery queries for Friendly."""

from dataclasses import dataclass, field
from datetime import date
from math import ceil

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from models import (
    ConnectionIntent,
    Interest,
    Language,
    Profile,
    User,
    profile_connection_intents,
    profile_interests,
    profile_languages,
)


PER_PAGE = 12
MAX_AGE = 120
SCORE_WEIGHTS = {"interest": 3, "language": 2, "intention": 1}


def years_ago(years, today=None):
    """Return the calendar date exactly ``years`` before today."""
    today = today or date.today()
    try:
        return today.replace(year=today.year - years)
    except ValueError:  # February 29 in a non-leap target year.
        return today.replace(year=today.year - years, day=28)


def normalized_city(value):
    """Normalize free-text cities for Sprint 6's case-insensitive comparison."""
    return (value or "").strip().casefold()


def _integer_values(values):
    identifiers = set()
    for value in values:
        try:
            if int(value) > 0:
                identifiers.add(int(value))
        except (TypeError, ValueError):
            continue
    return identifiers


@dataclass
class DiscoveryFilters:
    age_min: int | None = None
    age_max: int | None = None
    gender: str | None = None
    language_ids: set[int] = field(default_factory=set)
    interest_ids: set[int] = field(default_factory=set)
    intention_ids: set[int] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)

    @property
    def active(self):
        return any((self.age_min, self.age_max, self.gender, self.language_ids, self.interest_ids, self.intention_ids))

    def query_items(self):
        items = []
        if self.age_min is not None:
            items.append(("age_min", self.age_min))
        if self.age_max is not None:
            items.append(("age_max", self.age_max))
        if self.gender:
            items.append(("gender", self.gender))
        items.extend(("languages", item) for item in sorted(self.language_ids))
        items.extend(("interests", item) for item in sorted(self.interest_ids))
        items.extend(("intentions", item) for item in sorted(self.intention_ids))
        return items


def parse_filters(args, catalogues, valid_genders):
    """Validate untrusted GET values, retaining only known catalogue IDs."""
    filters = DiscoveryFilters()

    def parse_age(name, label):
        raw = (args.get(name) or "").strip()
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError:
            filters.errors.append(f"{label} age must be a whole number.")
            return None
        if not 18 <= value <= MAX_AGE:
            filters.errors.append(f"{label} age must be between 18 and {MAX_AGE}.")
            return None
        return value

    filters.age_min = parse_age("age_min", "Minimum")
    filters.age_max = parse_age("age_max", "Maximum")
    if filters.age_min and filters.age_max and filters.age_min > filters.age_max:
        filters.errors.append("Minimum age cannot be greater than maximum age.")
        filters.age_min = filters.age_max = None

    gender = args.get("gender")
    filters.gender = gender if gender in valid_genders else None
    filters.language_ids = _integer_values(args.getlist("languages")) & catalogues["languages"]
    filters.interest_ids = _integer_values(args.getlist("interests")) & catalogues["interests"]
    filters.intention_ids = _integer_values(args.getlist("intentions")) & catalogues["intentions"]
    return filters


def _association_count(table, column, identifiers):
    if not identifiers:
        return 0
    return (
        select(func.count())
        .where(table.c.profile_id == Profile.id, column.in_(identifiers))
        .correlate(Profile)
        .scalar_subquery()
    )


def _complete_profile_conditions():
    interest_count = select(func.count()).where(profile_interests.c.profile_id == Profile.id).correlate(Profile).scalar_subquery()
    return [
        Profile.open_to_connections.is_(True),
        Profile.profile_photo_key.is_not(None),
        func.trim(Profile.profile_photo_key) != "",
        Profile.gender.is_not(None),
        func.trim(Profile.gender) != "",
        Profile.home_country_code.is_not(None),
        func.trim(Profile.home_country_code) != "",
        Profile.home_city.is_not(None),
        func.trim(Profile.home_city) != "",
        Profile.discovery_country_code.is_not(None),
        func.trim(Profile.discovery_country_code) != "",
        Profile.discovery_city.is_not(None),
        func.trim(Profile.discovery_city) != "",
        User.date_of_birth.is_not(None),
        User.date_of_birth <= years_ago(18),
        Profile.languages.any(),
        interest_count.between(3, 12),
        Profile.connection_intents.any(),
    ]


def _complete_candidate_conditions(current_profile):
    return [
        Profile.user_id != current_profile.user_id,
        Profile.discovery_country_code == current_profile.discovery_country_code,
        func.lower(func.trim(Profile.discovery_city)) == normalized_city(current_profile.discovery_city),
        *_complete_profile_conditions(),
    ]


@dataclass
class DiscoveryResult:
    profile: Profile
    score: int
    reasons: list[str]


@dataclass
class DiscoveryPage:
    items: list[DiscoveryResult]
    page: int
    pages: int
    total: int
    per_page: int = PER_PAGE


def discover_profiles(session, current_profile, filters, page=1):
    """Return one ranked page from the eligible local candidate pool."""
    current_language_ids = {item.id for item in current_profile.languages}
    current_interest_ids = {item.id for item in current_profile.interests}
    current_intention_ids = {item.id for item in current_profile.connection_intents}

    shared_languages = _association_count(profile_languages, profile_languages.c.language_id, current_language_ids)
    shared_interests = _association_count(profile_interests, profile_interests.c.interest_id, current_interest_ids)
    shared_intentions = _association_count(
        profile_connection_intents,
        profile_connection_intents.c.connection_intent_id,
        current_intention_ids,
    )
    score = (
        shared_interests * SCORE_WEIGHTS["interest"]
        + shared_languages * SCORE_WEIGHTS["language"]
        + shared_intentions * SCORE_WEIGHTS["intention"]
    ).label("relevance_score")

    conditions = _complete_candidate_conditions(current_profile)
    if filters.age_min is not None:
        conditions.append(User.date_of_birth <= years_ago(filters.age_min))
    if filters.age_max is not None:
        conditions.append(User.date_of_birth > years_ago(filters.age_max + 1))
    if filters.gender:
        conditions.append(Profile.gender == filters.gender)
    if filters.language_ids:
        conditions.append(Profile.languages.any(Language.id.in_(filters.language_ids)))
    if filters.interest_ids:
        conditions.append(Profile.interests.any(Interest.id.in_(filters.interest_ids)))
    if filters.intention_ids:
        conditions.append(Profile.connection_intents.any(ConnectionIntent.id.in_(filters.intention_ids)))

    base = select(Profile).join(Profile.user).where(and_(*conditions))
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    pages = max(1, ceil(total / PER_PAGE))
    page = min(max(1, page), pages)
    statement = (
        select(Profile, score)
        .join(Profile.user)
        .where(and_(*conditions))
        .options(
            joinedload(Profile.user),
            selectinload(Profile.languages),
            selectinload(Profile.interests),
            selectinload(Profile.connection_intents),
        )
        .order_by(score.desc(), Profile.created_at.desc(), Profile.id.asc())
        .limit(PER_PAGE)
        .offset((page - 1) * PER_PAGE)
    )

    items = []
    for profile, relevance_score in session.execute(statement).all():
        languages = current_language_ids & {item.id for item in profile.languages}
        interests = current_interest_ids & {item.id for item in profile.interests}
        intentions = current_intention_ids & {item.id for item in profile.connection_intents}
        reasons = []
        if interests:
            reasons.append(f"{len(interests)} interest{'s' if len(interests) != 1 else ''} in common")
        if languages:
            names = sorted(item.name for item in profile.languages if item.id in languages)
            reasons.append(f"You both speak {names[0]}" if len(names) == 1 else f"{len(names)} languages in common")
        if intentions:
            name = next(item.name for item in profile.connection_intents if item.id in intentions)
            reasons.append(f"Also looking for {name.lower()}")
        items.append(DiscoveryResult(profile, int(relevance_score or 0), reasons))
    return DiscoveryPage(items, page, pages, total)


def public_profile(session, user_id):
    """Return a complete, open adult profile suitable for authenticated viewing."""
    statement = (
        select(Profile)
        .join(Profile.user)
        .where(Profile.user_id == user_id, and_(*_complete_profile_conditions()))
        .options(joinedload(Profile.user), selectinload(Profile.languages), selectinload(Profile.interests), selectinload(Profile.connection_intents))
    )
    return session.scalar(statement)
