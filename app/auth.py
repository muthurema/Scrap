"""Admin authentication (PBKDF2 password hashing, stored in the settings table)."""

import hashlib
import os
import secrets

from app import db

DEFAULT_ADMIN_PASSWORD = "admin123"
_ITERATIONS = 200_000


def _hash(password: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{salt.hex()}${dk.hex()}"


def set_admin_password(password: str):
    db.set_setting("admin_password_hash", _hash(password, os.urandom(16)))


def ensure_default_admin():
    if db.get_setting("admin_password_hash") is None:
        set_admin_password(DEFAULT_ADMIN_PASSWORD)
        db.set_setting("admin_password_is_default", "1")


def is_default_password() -> bool:
    return db.get_setting("admin_password_is_default") == "1"


def verify_password(password: str) -> bool:
    stored = db.get_setting("admin_password_hash")
    if not stored or "$" not in stored:
        return False
    salt_hex, dk_hex = stored.split("$", 1)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), _ITERATIONS)
    return secrets.compare_digest(candidate.hex(), dk_hex)


def change_password(new_password: str):
    set_admin_password(new_password)
    db.set_setting("admin_password_is_default", "0")
