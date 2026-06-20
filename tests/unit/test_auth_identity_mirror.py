"""ADR-0039 (#778/#1398) Slice 3 — the shared domain-`User` provisioning mirror.

`build_domain_user_upsert` builds the idempotent upsert from the core-IR User entity:
declared mode uses the `auth_identity:` map; undeclared mode keeps the #1398 best-effort.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.http.runtime.auth_identity_mirror import build_domain_user_upsert


def _user(dsl: str):
    n, a, t, c, u, frag = parse_dsl(dsl, Path("t.dsl"))
    return next(e for e in frag.entities if e.name == "User")


_DECLARED = """module t
app t "T"
entity User "User":
  id: uuid pk
  email: str(120) required
  username: str(40) required
  display_name: str(80) required
  role: str(40)
  created_at: datetime auto_add
  auth_identity:
    link_via: email
    map:
      username: email_localpart
      display_name: email_localpart
    default:
      role: viewer
"""

_UNDECLARED = """module t
app t "T"
entity User "User":
  id: uuid pk
  email: str(120) required
  name: str(80)
  role: str(40)
  is_active: bool=true
"""


class TestBuildDomainUserUpsert:
    def test_declared_uses_the_map(self) -> None:
        sql, params = build_domain_user_upsert(
            _user(_DECLARED),
            user_id="uid-1",
            email="alice@corp.test",
            username="ignored",  # declared map derives from email_localpart, not this
            role="ignored",
        )
        # link_via (email) + mapped username/display_name + default role + pk id.
        for col in ("id", "email", "username", "display_name", "role"):
            assert f'"{col}"' in sql, (col, sql)
        # email_localpart derivation + literal default flow into params.
        assert "uid-1" in params and "alice@corp.test" in params
        assert "alice" in params  # email_localpart → username/display_name
        assert "viewer" in params  # literal default
        assert "ON CONFLICT (id) DO UPDATE" in sql
        # auto_add created_at handled inline, not as a bound col.
        assert '"created_at"' in sql and "NOW()" in sql

    def test_undeclared_best_effort(self) -> None:
        sql, params = build_domain_user_upsert(
            _user(_UNDECLARED),
            user_id="uid-2",
            email="bob@corp.test",
            username="Bob",
            role="agent",
        )
        for col in ("id", "email", "name", "role", "is_active"):
            assert f'"{col}"' in sql, (col, sql)
        assert "Bob" in params and "agent" in params and True in params

    def test_no_id_column_returns_none(self) -> None:
        # An entity with no writable id can't be upserted deterministically.
        dsl = """module t
app t "T"
entity User "User":
  email: str(120) required pk
  auth_identity:
    link_via: email
"""
        # email is the pk here; build still works (id absent → keyed on email? no — we
        # require an `id` column). With email as pk and no `id`, returns None.
        result = build_domain_user_upsert(
            _user(dsl), user_id="x", email="x@y.z", username="x", role="r"
        )
        assert result is None
