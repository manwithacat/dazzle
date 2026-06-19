"""ADR-0039 (#778/#1398) Slice 3 — the runtime mirror the production hook invokes.

`AuthStore.create_user` calls `mirror_auth_user_to_domain(self._execute_modify, user_spec, ...)`
via the server-set `_on_user_created` hook. This exercises that runtime path against a
capturing executor: a declared `User` upserts the domain row; failures never propagate.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.back.runtime.auth_identity_mirror import mirror_auth_user_to_domain
from dazzle.core.dsl_parser_impl import parse_dsl


def _user(dsl: str):
    n, a, t, c, u, frag = parse_dsl(dsl, Path("t.dsl"))
    return next(e for e in frag.entities if e.name == "User")


_DECLARED = """module t
app t "T"
entity User "User":
  id: uuid pk
  email: str(120) required
  username: str(40) required
  auth_identity:
    link_via: email
    map:
      username: email_localpart
"""


class TestProductionMirror:
    def test_executes_upsert_via_callable(self) -> None:
        calls: list[tuple[str, tuple]] = []

        def execute(sql: str, params: tuple) -> int:
            calls.append((sql, params))
            return 1

        mirror_auth_user_to_domain(
            execute,
            _user(_DECLARED),
            user_id="uid-9",
            email="carol@corp.test",
            username="ignored",
            role="author",
        )
        assert len(calls) == 1
        sql, params = calls[0]
        assert 'INSERT INTO "User"' in sql and "ON CONFLICT (id)" in sql
        assert "uid-9" in params and "carol@corp.test" in params
        assert "carol" in params  # email_localpart → username

    def test_swallows_executor_errors(self) -> None:
        def boom(sql: str, params: tuple) -> int:
            raise RuntimeError("db down")

        # Must not raise — a mirror miss can't break auth-user creation (D1).
        mirror_auth_user_to_domain(
            boom,
            _user(_DECLARED),
            user_id="uid-10",
            email="dave@corp.test",
            username="d",
            role="author",
        )

    def test_unmirrorable_entity_skips_execute(self) -> None:
        calls: list = []
        dsl = """module t
app t "T"
entity User "User":
  email: str(120) required pk
  auth_identity:
    link_via: email
"""
        mirror_auth_user_to_domain(
            lambda sql, params: calls.append(sql),
            _user(dsl),
            user_id="x",
            email="x@y.z",
            username="x",
            role="r",
        )
        assert calls == []  # no `id` column → build returns None → no execute
