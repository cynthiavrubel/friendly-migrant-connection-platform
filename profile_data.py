"""Stable profile choices and idempotent seed definitions."""

import pycountry


GENDER_CHOICES = (
    ("woman", "Woman"),
    ("man", "Man"),
    ("non_binary", "Non-binary"),
    ("self_described", "Self-described"),
    ("prefer_not_to_say", "Prefer not to say"),
)

EUROPEAN_COUNTRY_CODES = {
    "AL", "AD", "AT", "BY", "BE", "BA", "BG", "HR", "CY", "CZ", "DK",
    "EE", "FI", "FR", "DE", "GR", "HU", "IS", "IE", "IT", "XK", "LV",
    "LI", "LT", "LU", "MT", "MD", "MC", "ME", "NL", "MK", "NO", "PL",
    "PT", "RO", "RU", "SM", "RS", "SK", "SI", "ES", "SE", "CH", "TR",
    "UA", "GB", "VA",
}


def country_choices():
    """Return global ISO countries with Europe first for the current product focus."""
    countries = [(country.alpha_2, country.name) for country in pycountry.countries]
    return sorted(countries, key=lambda item: (item[0] not in EUROPEAN_COUNTRY_CODES, item[1]))


def country_name(code):
    """Resolve a stored ISO alpha-2 code to a human-readable name."""
    country = pycountry.countries.get(alpha_2=code) if code else None
    return country.name if country else code


LANGUAGES = (
    ("English", "en"), ("Ukrainian", "uk"), ("Irish", "ga"), ("Polish", "pl"),
    ("Spanish", "es"), ("French", "fr"), ("German", "de"), ("Italian", "it"),
    ("Portuguese", "pt"), ("Romanian", "ro"), ("Dutch", "nl"), ("Czech", "cs"),
    ("Slovak", "sk"), ("Hungarian", "hu"), ("Greek", "el"), ("Bulgarian", "bg"),
    ("Croatian", "hr"), ("Serbian", "sr"), ("Lithuanian", "lt"), ("Latvian", "lv"),
    ("Estonian", "et"), ("Swedish", "sv"), ("Norwegian", "no"), ("Danish", "da"),
    ("Finnish", "fi"), ("Turkish", "tr"), ("Arabic", "ar"),
)

INTERESTS = {
    "Social": ("Coffee", "Restaurants", "Nightlife", "Board games", "Trivia"),
    "Active": ("Gym", "Running", "Hiking", "Cycling", "Football", "Swimming", "Yoga"),
    "Culture": ("Cinema", "Museums", "Theatre", "Art", "Photography", "Live music"),
    "Lifestyle": ("Cooking", "Travel", "Reading", "Fashion", "Technology", "Gaming"),
    "Community": ("Volunteering", "Language exchange", "Faith & spirituality", "Parenting"),
}

CONNECTION_INTENTS = (
    ("Meet new people", "meet-new-people"),
    ("Find activity buddies", "find-activity-buddies"),
    ("Explore the city", "explore-the-city"),
    ("New to the area", "new-to-the-area"),
    ("Travelling / visiting", "travelling-visiting"),
    ("Language exchange", "language-exchange"),
    ("Welcome newcomers", "welcome-newcomers"),
)


def slugify_interest(name):
    """Return the stable slugs used by the initial interest catalogue."""
    return name.lower().replace("&", "and").replace("/", " ").replace(" ", "-")
