"""Native document signing primitive (#1283, phase 2).

Public API surface for the ``signable: true`` DSL primitive's runtime
support. The DSL keyword wiring lands in phase 3 (parser + IR + linker);
this package is the standalone, framework-agnostic backend that the
auto-generated routes will call.

Heavy crypto dependencies (``fpdf2``, ``pyhanko``, ``cryptography``)
live behind the ``[signing]`` extra. ``tokens.py`` is dep-free and is
always importable; ``cert.py`` needs ``cryptography``; ``service.py``
needs ``fpdf2`` + ``pyhanko``. Each module raises ``SigningError`` with
a friendly install hint when its deps are missing.

Env vars consumed at runtime:

    SIGNING_TOKEN_SECRET   HMAC key for signing tokens
    SIGNING_CERT_PFX_B64   Base64-encoded PKCS#12 signing cert + CA chain
    SIGNING_CERT_PASSWORD  PKCS#12 encryption password
"""

from __future__ import annotations

from dazzle.signing.tokens import (
    DEFAULT_EXPIRY_HOURS,
    TOKEN_SECRET_ENV_VAR,
    InvalidTokenError,
    SigningError,
    mint_token,
    token_hash,
    verify_token,
    verify_token_allow_expired,
)

__all__ = (
    "DEFAULT_EXPIRY_HOURS",
    "InvalidTokenError",
    "SigningError",
    "TOKEN_SECRET_ENV_VAR",
    "mint_token",
    "token_hash",
    "verify_token",
    "verify_token_allow_expired",
)
