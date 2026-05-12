"""Env-var interpolation for `[storage.<name>]` config blocks (#932).

Storage config strings (bucket, region, endpoint_url) may reference
environment variables via `${VAR}` syntax. This module:

1. Resolves `${VAR}` references at read time.
2. Surfaces every required var so `dazzle storage env-vars` can
   generate a `.env.example` and `dazzle storage check` can fail fast
   on missing values.

Mirrors the pattern already used by `AuthSpec.credentials` (which
takes `env("KEY")` references) and the API-pack env-vars CLI.
"""

from __future__ import annotations

import os
import re

# Match ${VAR_NAME} — uppercase letters, digits, underscores, no
# default-value-fallback syntax (we want every reference to be
# explicit so missing vars are loud, not silently empty).
_VAR_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


class EnvVarMissingError(LookupError):
    """Raised when interpolating a string that references a
    `${VAR}` not present in the environment.

    Attributes:
        var_name: The missing variable's name.
        context: Optional human-readable description of where the
            reference occurred (e.g. `"[storage.cohort_pdfs] bucket"`).
    """

    def __init__(self, var_name: str, context: str = ""):
        self.var_name = var_name
        self.context = context
        msg = f"Required environment variable {var_name!r} is not set"
        if context:
            msg += f" (referenced from {context})"
        super().__init__(msg)


def extract_env_var_refs(value: str | None) -> list[str]:
    """Return the list of `${VAR}` names referenced in *value*, in
    document order. Duplicates collapse — caller can re-add them via
    a set if order doesn't matter."""
    if not value:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in _VAR_PATTERN.finditer(value):
        var = match.group(1)
        if var not in seen:
            seen.add(var)
            out.append(var)
    return out


def interpolate_env_vars(value: str | None, *, context: str = "") -> str | None:
    """Substitute every `${VAR}` reference in *value* with the
    corresponding environment-variable value.

    Returns ``None`` unchanged. Raises `EnvVarMissingError` if any
    referenced var is unset (no silent empty-string fallback — that
    would mask configuration bugs).
    """
    if value is None:
        return None
    if "${" not in value:
        return value

    def _replace(match: re.Match[str]) -> str:
        var = match.group(1)
        if var not in os.environ:
            raise EnvVarMissingError(var, context=context)
        return os.environ[var]

    return _VAR_PATTERN.sub(_replace, value)
