"""Interactive-user password hashing: argon2, with the legacy SHA256 verified
for as long as a row still holds one.

`tblUsers.StoredPassword` held `SHA256(password + PrivateKey)` in uppercase hex
for the legacy .NET application, which read the same table. That application is
no longer supported, so the format is ours to change. New and changed passwords
are hashed with argon2id; a legacy hash keeps verifying and is rewritten the
first time it does, which is the only moment the raw password is in hand.
Nothing rehashes offline, so an account that never logs in again keeps its
legacy hash and still authenticates with it.

Django's hasher is instantiated here rather than resolved through
PASSWORD_HASHERS: that setting governs TechnicalUser, a Django user on PBKDF2
already, and this module must behave the same whatever an assembly puts there.

`password_hasher` in the core module configuration keeps the legacy format for
a deployment that needs it. Both values verify both formats, so changing it
locks nobody out.
"""

import logging
from collections import namedtuple
from hashlib import sha256

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
    return CoreConfig.password_hasher or ARGON2


def legacy_hash(raw, salt):
    """The legacy application's format.

    `salt` is formatted, not coerced: a null salt hashed as the string "None"
    there, and every existing row has to keep verifying byte for byte.
    """
    return sha256(f"{raw.rstrip()}{salt}".encode()).hexdigest().upper()


def hash_password(raw, salt):
    """The stored form of `raw` under the configured hasher."""
    if configured() == SHA256:
        return legacy_hash(raw, salt)
    # rstrip for parity with the legacy format: the password a legacy row
    # verifies with is the one its rehash has to verify with too.
    return _argon2.encode(raw.rstrip(), _argon2.salt())


def verify(raw, encoded, salt):
    """Whether `raw` matches `encoded`, and whether the row should be rewritten.

    A rewrite is asked for only while argon2 is configured: for a legacy hash,
    or for an argon2 hash whose parameters Django has since raised. Under the
    legacy hasher nothing moves in either direction.
    """
    if not encoded:
        return Verification(False, False)
    upgrade = configured() == ARGON2
    if encoded.startswith(_ARGON2_PREFIX):
        try:
            ok = _argon2.verify(raw.rstrip(), encoded)
        except ValueError:
            # A string carrying the prefix but not the shape raises rather than
            # returning False. A corrupt row is a failed login, not a 500.
            ok = False
        return Verification(ok, ok and upgrade and _argon2.must_update(encoded))
    ok = constant_time_compare(legacy_hash(raw, salt), encoded.upper())
    return Verification(ok, ok and upgrade)


def configure(cfg):
    """Apply the hasher key of a core configuration to CoreConfig.

    Called from CoreConfig.ready() with the effective configuration, and again
    when the configuration row is saved, so a change takes effect without a
    restart.
    """
    CoreConfig.password_hasher = cfg["password_hasher"]
    logger.info("Interactive-user password hasher: %s", CoreConfig.password_hasher)


def validate_configuration(instance):
    """Refuse a core configuration row naming a hasher this module lacks.

    Registered for the core module; ModuleConfiguration.clean() calls it on
    every save. Only the row's own keys are checked, since the row is merged
    over the defaults.
    """
    cfg = instance._cfg
    if not isinstance(cfg, dict):
        # The body's shape is another validator's to report; a non-object here
        # would only raise AttributeError out of save().
        return
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
