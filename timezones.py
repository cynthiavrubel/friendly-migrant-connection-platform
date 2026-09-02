"""IANA timezone validation, DST-safe conversion, and plan-local formatting."""

from datetime import timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones


DEFAULT_TIMEZONE = "Europe/Dublin"
MAX_TIMEZONE_LENGTH = 64
COMMON_TIMEZONES = (
    "Europe/Dublin", "Europe/London", "Europe/Kyiv", "Europe/Paris",
    "Europe/Rome", "Europe/Warsaw", "America/New_York", "America/Chicago",
    "America/Denver", "America/Los_Angeles", "America/Toronto",
    "Africa/Lagos", "Asia/Dubai", "Asia/Kolkata", "Asia/Tokyo",
    "Australia/Sydney", "UTC",
)


class TimezoneError(ValueError):
    """A user-safe invalid, nonexistent, or ambiguous local-time error."""

    def __init__(self, message, code="invalid_timezone"):
        super().__init__(message)
        self.message = message
        self.code = code


@lru_cache(maxsize=1)
def timezone_choices():
    """Return every installed canonical key, with common choices first."""
    installed = available_timezones()
    common = [key for key in COMMON_TIMEZONES if key in installed]
    return tuple(common + sorted(installed - set(common)))


@lru_cache(maxsize=256)
def get_timezone(key):
    if not isinstance(key, str) or not key or len(key) > MAX_TIMEZONE_LENGTH:
        raise TimezoneError("Choose a valid timezone.")
    # Membership validation prevents treating submitted values as paths or offsets.
    if key not in set(timezone_choices()):
        raise TimezoneError("Choose a valid timezone.")
    try:
        return ZoneInfo(key)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise TimezoneError("Choose a valid timezone.") from error


def is_valid_timezone(key):
    try:
        get_timezone(key)
        return True
    except TimezoneError:
        return False


def normalize_utc(value):
    """Normalize MySQL/SQLite naive UTC results into aware UTC datetimes."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def local_to_utc(local_datetime, timezone_key):
    """Resolve one local wall time, rejecting DST gaps and duplicated times."""
    zone = get_timezone(timezone_key)
    if local_datetime is None:
        raise TimezoneError("Choose a date and time.", "missing")
    if local_datetime.tzinfo is not None:
        # Internal callers may already hold an instant; browser form values are naive.
        return local_datetime.astimezone(timezone.utc)
    valid_instants = set()
    for fold in (0, 1):
        candidate = local_datetime.replace(tzinfo=zone, fold=fold)
        instant = candidate.astimezone(timezone.utc)
        round_trip = instant.astimezone(zone).replace(tzinfo=None)
        if round_trip == local_datetime:
            valid_instants.add(instant)
    if not valid_instants:
        raise TimezoneError(
            "That local time does not exist because the clocks change on this date. Please choose another time.",
            "nonexistent",
        )
    if len(valid_instants) > 1:
        raise TimezoneError(
            "That local time occurs twice because the clocks change on this date. Please choose a different time.",
            "ambiguous",
        )
    return valid_instants.pop()


def utc_to_local(utc_datetime, timezone_key):
    return normalize_utc(utc_datetime).astimezone(get_timezone(timezone_key))


def format_plan_datetime(utc_datetime, timezone_key, *, compact=False):
    local = utc_to_local(utc_datetime, timezone_key)
    # Unicode escapes keep these separators stable across Windows code pages.
    pattern = "%a %d %b \u00b7 %H:%M" if compact else "%A, %d %B %Y at %H:%M"
    return f"{local.strftime(pattern)} \u2014 {timezone_key}"
