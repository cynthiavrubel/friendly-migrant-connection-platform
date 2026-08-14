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


# ISO 639-1 gives Friendly broad modern coverage without exposing pycountry's
# thousands of historical, local, bibliographic and technical ISO 639-3 rows.
# These entries are historical/liturgical or constructed rather than practical
# spoken-language choices for this product.
EXCLUDED_LANGUAGE_CODES = {
    "ae",  # Avestan
    "cu",  # Church Slavic
    "eo",  # Esperanto
    "ia",  # Interlingua
    "ie",  # Interlingue
    "io",  # Ido
    "la",  # Latin
    "pi",  # Pali
    "sa",  # Sanskrit
    "vo",  # Volapuk
    "zh",  # Replaced by clear Mandarin and Cantonese choices below.
}

LANGUAGE_NAME_OVERRIDES = {
    "el": "Greek",
    "fa": "Persian (Farsi)",
    "ht": "Haitian Creole",
    "ky": "Kyrgyz",
    "ms": "Malay",
    "my": "Burmese (Myanmar)",
    "ne": "Nepali",
    "ny": "Chichewa",
    "or": "Odia",
    "pa": "Punjabi",
    "ps": "Pashto",
    "sw": "Swahili",
    "tl": "Filipino (Tagalog)",
    "ug": "Uyghur",
}

ADDITIONAL_SPOKEN_LANGUAGES = (
    ("Mandarin Chinese", "cmn"),
    ("Cantonese", "yue"),
)


def language_catalogue():
    """Return practical global spoken languages backed by stable ISO codes."""
    languages = []
    for language in pycountry.languages:
        code = getattr(language, "alpha_2", None)
        if not code or code in EXCLUDED_LANGUAGE_CODES:
            continue
        name = LANGUAGE_NAME_OVERRIDES.get(code, language.name)
        languages.append((name, code))
    languages.extend(ADDITIONAL_SPOKEN_LANGUAGES)
    return tuple(sorted(languages, key=lambda item: item[0].casefold()))


LANGUAGES = language_catalogue()

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
