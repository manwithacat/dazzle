"""Database-URL scheme normalisation helpers.

Heroku (and other PaaS providers) hand out database URLs with the deprecated
``postgres://`` scheme. SQLAlchemy and psycopg require ``postgresql://``.
Some call sites additionally need the psycopg v3 driver suffix
(``postgresql+psycopg://``).

These two helpers consolidate logic that was previously copy-pasted inline
across ~16 modules. They live in ``core`` — the lowest layer — so ``back``,
``cli`` and ``ui`` can all import them without circular-import risk.
"""

_POSTGRES_PREFIX = "postgres://"
_POSTGRESQL_PREFIX = "postgresql://"
_PSYCOPG_PREFIX = "postgresql+psycopg://"


def normalise_postgres_scheme(url: str) -> str:
    """Rewrite a leading ``postgres://`` to ``postgresql://``.

    Heroku hands out the deprecated ``postgres://`` alias; SQLAlchemy and
    psycopg expect ``postgresql://``.

    Idempotent: a URL that already uses ``postgresql://`` (or any other
    scheme) is returned unchanged. Callers are assumed to pass a ``str``.
    """
    if url.startswith(_POSTGRES_PREFIX):
        return _POSTGRESQL_PREFIX + url[len(_POSTGRES_PREFIX) :]
    return url


def add_psycopg_driver(url: str) -> str:
    """Rewrite a bare ``postgresql://`` to ``postgresql+psycopg://``.

    SQLAlchemy uses psycopg2 by default; this pins it to the psycopg v3
    driver.

    Idempotent and driver-aware: a URL that already specifies a ``+driver``
    (e.g. ``postgresql+psycopg://`` or ``postgresql+asyncpg://``) is returned
    unchanged. Only a bare ``postgresql://`` scheme is rewritten.
    """
    if url.startswith(_POSTGRESQL_PREFIX):
        return _PSYCOPG_PREFIX + url[len(_POSTGRESQL_PREFIX) :]
    return url
