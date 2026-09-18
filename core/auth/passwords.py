"""Password hashing for interactive users.

Passwords are hashed with argon2id. Rows still holding the earlier format, an
uppercase-hex SHA256 of the password and the salt column, keep verifying and are
rewritten the first time they do, which is the only moment the raw password is
in hand. Nothing rehashes offline, so an account that never logs in again keeps
the old hash and still authenticates with it.

Django's hasher is instantiated here rather than resolved through
PASSWORD_HASHERS, which orders the hashers for TechnicalUser and is an
assembly's to configure. This module must behave the same whatever it says.

`password_hasher` in the core module configuration selects the format new
passwords are written in. Both values verify both formats, so changing it locks
nobody out.
"""

import hashlib
import logging
from collections import namedtuple

from django.contrib.auth.hashers import Argon2PasswordHasher
from django.core.exceptions import ValidationError
from django.utils.crypto import constant_time_compare

from core.apps import CoreConfig

logger = logging.getLogger(__name__)

ARGON2 = "argon2"
SHA256 = "sha256"
HASHERS = (ARGON2, SHA256)

_argon2 = Argon2PasswordHasher()
_ARGON2_PREFIX = _argon2.algorithm + "$"

#: `rehash` is only ever True when `ok` is: a wrong password proves nothing
#: about the stored format and must never cause a write.
Verification = namedtuple("Verification", "ok rehash")


def configured():
    """The hasher in force, falling back to argon2 for anything unrecognised.

    The configuration row is validated on save, but one written by a fixture or
    by direct SQL is not. Falling back rather than trusting the string keeps an
    unknown value from quietly disabling every rewrite.
    """
    hasher = CoreConfig.password_hasher
    if hasher not in HASHERS:
        if hasher is not None:
            logger.warning("Unknown password_hasher %r; using %s.", hasher, ARGON2)
        return ARGON2
    return hasher


def _prepared(raw):
    """Trailing whitespace is stripped before hashing.

    The earlier format did it, so a password that verified against an old row
    has to hash the same way when that row is rewritten.
    """
    return raw.rstrip()


def _legacy_hash(raw, salt):
    """The earlier format.

    `salt` is interpolated, not coerced: a null salt hashed as the string
    "None", and existing rows have to keep verifying byte for byte.
    """
    return hashlib.sha256(f"{_prepared(raw)}{salt}".encode()).hexdigest().upper()


def _verify_argon2(raw, encoded):
    try:
        return _argon2.verify(_prepared(raw), encoded)
    except ValueError:
        # A string carrying the prefix but not the shape raises rather than
        # returning False. A corrupt row is a failed login, not a 500.
        return False


def hash_password(raw, salt):
    """The stored form of `raw` under the configured hasher.

    `salt` is only used by the legacy format; argon2 carries its own.
    """
    if configured() == SHA256:
        return _legacy_hash(raw, salt)
    return _argon2.encode(_prepared(raw), _argon2.salt())


def verify(raw, encoded, salt):
    """Whether `raw` matches `encoded`, and whether the row should be rewritten.

    A rewrite is asked for only while argon2 is configured: for a legacy hash,
    or for an argon2 hash whose parameters Django has since raised. Under the
    legacy hasher nothing moves in either direction.
    """
    if not encoded:
        return Verification(False, False)
    rewrite = configured() == ARGON2
    if encoded.startswith(_ARGON2_PREFIX):
        ok = _verify_argon2(raw, encoded)
        return Verification(ok, ok and rewrite and _argon2.must_update(encoded))
    ok = constant_time_compare(_legacy_hash(raw, salt), encoded.upper())
    return Verification(ok, ok and rewrite)


def configure(cfg):
    """Apply the hasher key of a core configuration to CoreConfig.

    Called from CoreConfig.ready() with the effective configuration, and again
    when the configuration row is saved, so a change takes effect without a
    restart.
    """
    CoreConfig.password_hasher = cfg["password_hasher"]
    logger.info("Interactive-user password hasher: %s", CoreConfig.password_hasher)


def validate_configuration(instance):
    """Refuse a core configuration row this module could not act on.

    Registered for the core module; ModuleConfiguration.clean() calls it on
    every save. Only the row's own keys are checked, since the row is merged
    over the defaults.
    """
    cfg = instance._cfg
    if not isinstance(cfg, dict):
        # clean() guards the JSON syntax but not its shape, so a valid-JSON list
        # arrives here intact. Merging it over the defaults raises a TypeError
        # that start-up swallows, silently dropping the whole core
        # configuration, so refuse it as a field error instead.
        raise ValidationError({"config": "The configuration must be a JSON object."})
    hasher = cfg.get("password_hasher", ARGON2)
    if hasher not in HASHERS:
        raise ValidationError(
            {
                "config": "password_hasher must be one of "
                f"{', '.join(HASHERS)}, not {hasher!r}."
            }
        )


def reload_configuration(instance):
    """Re-apply the effective core configuration after a row is committed.

    Read the way CoreConfig.ready() reads it rather than from the saved
    instance: a row disabled with is_disabled_until, or a second row, resolves
    exactly as it will at the next start.
    """
    from core.apps import DEFAULT_CFG, MODULE_NAME
    from core.models import ModuleConfiguration

    configure(ModuleConfiguration.get_or_default(MODULE_NAME, DEFAULT_CFG))
