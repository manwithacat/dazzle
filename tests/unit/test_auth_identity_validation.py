"""ADR-0039 (#778/#1398) Slice 2 — validate-time completeness of the auth_identity bridge (D6/A1).

An incomplete binding is a static error, never a swallowed runtime insert failure.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import ModuleIR
from dazzle.core.linker import build_appspec
from dazzle.core.validation.entities import validate_auth_identity_binding


def _appspec(dsl: str):
    n, a, t, c, u, frag = parse_dsl(dsl, Path("t.dsl"))
    return build_appspec(
        [
            ModuleIR(
                name=n or "t",
                file=Path("t.dsl"),
                app_name=a,
                app_title=t,
                app_config=c,
                uses=u,
                fragment=frag,
            )
        ],
        "t",
    )


def _errors(dsl: str) -> list[str]:
    errors, _warnings = validate_auth_identity_binding(_appspec(dsl))
    return errors


_CLEAN = """module t
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
"""


class TestAuthIdentityValidation:
    def test_fully_resolved_global_user_is_clean(self) -> None:
        # email=link_via, username/display_name mapped, role optional, created_at auto.
        assert _errors(_CLEAN) == []

    def test_unresolved_required_column_errors(self) -> None:
        # display_name is required-no-default but neither mapped nor defaulted.
        dsl = """module t
app t "T"
entity User "User":
  id: uuid pk
  email: str(120) required
  display_name: str(80) required
  auth_identity:
    link_via: email
    map:
      email: email
"""
        errs = _errors(dsl)
        assert any("display_name" in e and "not resolved" in e for e in errs), errs

    def test_link_via_not_a_column_errors(self) -> None:
        dsl = """module t
app t "T"
entity User "User":
  id: uuid pk
  email: str(120) required
  auth_identity:
    link_via: not_a_column
"""
        errs = _errors(dsl)
        assert any("link_via" in e and "not a column" in e for e in errs), errs

    def test_two_bindings_error(self) -> None:
        dsl = """module t
app t "T"
entity User "User":
  id: uuid pk
  email: str(120) required
  auth_identity:
    link_via: email
entity Account "Account":
  id: uuid pk
  email: str(120) required
  auth_identity:
    link_via: email
"""
        assert any("more than one entity" in e for e in _errors(dsl))

    def test_fenced_user_rejected(self) -> None:
        # User is fenced under a tenant root (required ref to a tenant_host entity)
        # → can't be the global principal (ADR-0039 D6).
        dsl = """module t
app t "T"
entity Org "Org":
  id: uuid pk
  slug: slug
  tenant_host:
    domain: example.com
    slug_field: slug
    canonical_hosts: [localhost]
    order: 1
entity User "User":
  id: uuid pk
  email: str(120) required
  org: ref Org required
  auth_identity:
    link_via: email
"""
        assert any("global/unfenced" in e for e in _errors(dsl)), _errors(dsl)

    def test_no_binding_no_errors(self) -> None:
        dsl = """module t
app t "T"
entity User "User":
  id: uuid pk
  email: str(120) required
"""
        assert _errors(dsl) == []
