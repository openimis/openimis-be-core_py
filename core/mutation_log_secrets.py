import json
import logging

logger = logging.getLogger(__name__)

MASK = "********"

# Matched lowercased, by substring: `password`, `old_password`, `newPassword`
# and `user_password` are all covered by "password".
#
# Masking can only remove audit detail, never add any: when in doubt about a
# field name, better to include it. The list is deliberately broad, and the only
# fields actually concerned today in a logged mutation input are `password`
# (core) and `api_key` (payroll).
SECRET_KEY_HINTS = (
    "password",
    "passwd",
    "passphrase",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "privatekey",
    "credential",
    "otp",
)

# Maximum descent depth: a mutation payload is a shallow JSON tree, and a bound
# keeps an unexpected structure from recursing without end.
_MAX_DEPTH = 20


def is_secret_key(key):
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return any(hint in lowered for hint in SECRET_KEY_HINTS)


def scrub_secrets(value, _depth=0):
    """Return a copy of `value` with the values under a sensitive key masked.

    The key itself is kept: the log has to stay readable and show that a
    password was indeed sent, without showing its value.
    """
    if _depth > _MAX_DEPTH:
        return value
    if isinstance(value, dict):
        return {
            key: (MASK if is_secret_key(key) else scrub_secrets(inner, _depth + 1))
            for key, inner in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [scrub_secrets(item, _depth + 1) for item in value]
    return value


def contains_secret(value, _depth=0):
    """True if the structure carries at least one sensitive key, at any level."""
    if _depth > _MAX_DEPTH:
        return False
    if isinstance(value, dict):
        return any(
            is_secret_key(key) or contains_secret(inner, _depth + 1)
            for key, inner in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_secret(item, _depth + 1) for item in value)
    return False


def scrub_json_text(text):
    """Mask the secrets of a serialised JSON document.

    Leaves `text` untouched when it is not usable JSON - the log sometimes
    holds free text - and returns `None` when nothing changed, so the caller
    can skip a pointless write.
    """
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    scrubbed = scrub_secrets(parsed)
    if scrubbed == parsed:
        return None
    return json.dumps(scrubbed)


def contains_secret_key(text):
    """Cheap test, so that only the rows worth it are read back in full."""
    if not text:
        return False
    lowered = text.lower()
    return any(hint in lowered for hint in SECRET_KEY_HINTS)
