"""Password hashing and verification."""

import hashlib
import secrets


def hash_password(password: str, salt: str | None = None) -> str:
    """Hash a password with salt."""
    if salt is None:
        salt = secrets.token_hex(16)

    # Use PBKDF2 with SHA-256
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,  # iterations
    )

    return f"{salt}${key.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    try:
        salt, _ = password_hash.split("$")
        return hash_password(password, salt) == password_hash
    except ValueError:
        return False
