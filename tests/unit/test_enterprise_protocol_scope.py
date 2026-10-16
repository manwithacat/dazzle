"""Gate (DD-013, plan §3): no SAML implementation symbol in src/ or tests/.

SAML is out of scope for enterprise auth; SAML-only IdPs go through a broker that speaks
OIDC. Exempt: the Alembic revision that dropped the SAML replay table (history), the
framework-table registry that keeps naming it so autogenerate never targets it (#1357),
and the manifest test that proves ``[auth.enterprise]`` rejects the protocol by name.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

_REPO = Path(__file__).resolve().parents[2]
_TOKENS = re.compile(
    "|".join(
        ("sa" + "ml", "one" + "login", "xml" + "sec", "InResponse" + "To", "sp_entity" + "_id")
    )
)
_EXEMPT = {
    "src/dazzle/http/alembic/versions/0023_flense_park_enterprise_auth.py",
    "src/dazzle/http/alembic/framework_tables.py",  # names 0023's dropped table (#1357)
    "tests/unit/test_manifest_sections.py",
}


def test_no_out_of_scope_sso_symbol_in_src_or_tests() -> None:
    hits = [
        f"{rel}:{n}"
        for root in ("src", "tests")
        for path in sorted((_REPO / root).rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
        if (rel := path.relative_to(_REPO).as_posix()) not in _EXEMPT
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1)
        if _TOKENS.search(line)
    ]
    assert not hits, f"SAML symbols are out of scope (DD-013): {hits}"
