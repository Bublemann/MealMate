"""Input rules for meals (MEAL-01, MEAL-02, MEAL-05, SEC-13).

Names are stored as typed (trimmed) and searched through `normalize()` (`meals.name_norm`,
not unique: names may repeat). Instructions are multi-line plain text; the source link is any
`http(s)` URL with a host and without credentials.
"""

from urllib.parse import urlsplit

from app.domain.catalog import check_text, has_control_characters

MEAL_NAME_MAX_LENGTH = 80
INSTRUCTIONS_MAX_LENGTH = 10_000
SOURCE_URL_MAX_LENGTH = 2_000
SERVINGS_MIN = 1
SERVINGS_MAX = 99
MEAL_TAGS_MAX = 10
MEAL_ROWS_MAX = 100
ROW_NOTE_MAX_LENGTH = 80
# Exclusive lower bound 0, inclusive upper bound.
ROW_AMOUNT_MAX = 100_000.0

_SOURCE_URL_SCHEMES = frozenset({"http", "https"})


def check_instructions(text: str) -> str:
    """A validator for instructions: line breaks are kept (`\\r\\n` and `\\r` become `\\n`),
    any other control or format character is refused."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if any(has_control_characters(line) for line in text.split("\n")):
        raise ValueError("control or format characters")
    return text


def check_source_url(text: str) -> str:
    """A validator for source links (MEAL-05): an absolute `http` or `https` URL with a host,
    without user info (`user:pass@`), whitespace or control characters."""
    check_text(text)
    if any(char.isspace() for char in text):
        raise ValueError("whitespace")
    try:
        parts = urlsplit(text)
        parts.port  # noqa: B018 -- raises ValueError for an invalid port
    except ValueError:
        raise ValueError("not a URL") from None
    if parts.scheme not in _SOURCE_URL_SCHEMES:
        raise ValueError("only http and https links are allowed")
    if not parts.hostname:
        raise ValueError("no host")
    if "@" in parts.netloc:
        raise ValueError("user info is not allowed")
    return text
