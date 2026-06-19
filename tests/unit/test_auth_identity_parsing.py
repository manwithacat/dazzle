"""ADR-0039 (#778/#1398) Slice 1 — parse the `auth_identity:` entity block into IR.

The block declares the auth↔domain `User` bridge: link field + auth-attr→column map +
literal defaults. An unknown `map` source is a parse error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir import AuthIdentitySpec


def _entities(dsl: str):
    n, a, t, c, u, frag = parse_dsl(dsl, Path("t.dsl"))
    return {e.name: e for e in frag.entities}


_USER_DSL = """module t
app t "T"
entity User "User":
  id: uuid pk
  email: str(120) required
  username: str(40) required
  display_name: str(80) required
  role: str(40)
  auth_identity:
    link_via: email
    map:
      username: email_localpart
      display_name: email_localpart
    default:
      role: viewer
"""


class TestAuthIdentityParsing:
    def test_block_parses_into_spec(self) -> None:
        user = _entities(_USER_DSL)["User"]
        assert isinstance(user.auth_identity, AuthIdentitySpec)
        b = user.auth_identity
        assert b.link_via == "email"
        assert ("username", "email_localpart") in b.field_map
        assert ("display_name", "email_localpart") in b.field_map
        assert ("role", "viewer") in b.defaults

    def test_link_via_defaults_to_email(self) -> None:
        dsl = """module t
app t "T"
entity User "User":
  id: uuid pk
  email: str(120) required
  auth_identity:
    map:
      email: email
"""
        user = _entities(dsl)["User"]
        assert user.auth_identity is not None
        assert user.auth_identity.link_via == "email"

    def test_unknown_map_source_is_parse_error(self) -> None:
        dsl = """module t
app t "T"
entity User "User":
  id: uuid pk
  email: str(120) required
  auth_identity:
    map:
      email: not_a_real_source
"""
        with pytest.raises(ParseError, match="not one of"):
            _entities(dsl)

    def test_absent_block_leaves_none(self) -> None:
        dsl = """module t
app t "T"
entity User "User":
  id: uuid pk
  email: str(120) required
"""
        assert _entities(dsl)["User"].auth_identity is None
