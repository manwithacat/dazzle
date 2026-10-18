"""#1797: `role(a) or role(b)` / `role(a, b)` are alternatives; effects wire by entity.

U12 — the parser skipped `or` between guards, so `role(a) or role(b)` became two
guards that were ANDed, and `role(a, b)` (the documented form) did not parse at all.
U11 — `_init_transition_effects` looked services up by entity name in the
service-name-keyed dict, so no `on_transition` effect ever attached, silently.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.http.runtime.state_machine import TransitionValidator
from dazzle.http.specs.entity import StateMachineSpec, StateTransitionSpec, TransitionGuardSpec


def _parse_guards(constraint: str) -> list[ir.TransitionGuard]:
    src = f"""module t
app t "T"

entity Doc "Doc":
  id: uuid pk
  status: enum[draft, sent] = draft

  transitions:
    draft -> sent: {constraint}
"""
    *_, fragment = parse_dsl(src, Path("t.dsl"))
    ent = next(e for e in fragment.entities if e.name == "Doc")
    return list(ent.state_machine.transitions[0].guards)


@pytest.mark.parametrize(
    ("constraint", "expected"),
    [
        ("role(agent)", ("agent",)),
        ("role(agent, manager)", ("agent", "manager")),
        ("role(agent) or role(manager)", ("agent", "manager")),
        ("role(a) or role(b) or role(c)", ("a", "b", "c")),
        ("role(agent, manager) or role(admin)", ("agent", "manager", "admin")),
    ],
    ids=["single", "comma", "or", "or-chain", "mixed"],
)
def test_role_alternatives_parse_to_one_guard(constraint: str, expected: tuple[str, ...]) -> None:
    guards = _parse_guards(constraint)
    assert len(guards) == 1
    assert guards[0].role_alternatives == expected
    assert guards[0].requires_role == expected[0]


def test_requires_and_role_stay_anded() -> None:
    guards = _parse_guards("requires assignee role(agent)")
    assert [g.requires_field for g in guards] == ["assignee", None]
    assert guards[1].role_alternatives == ("agent",)


def test_or_outside_role_guards_is_a_parse_error() -> None:
    with pytest.raises(Exception, match="'or' joins role guards only"):
        _parse_guards("requires assignee or role(agent)")


def _validator(guard: TransitionGuardSpec) -> TransitionValidator:
    sm = StateMachineSpec(
        status_field="status",
        states=["draft", "sent"],
        transitions=[StateTransitionSpec(from_state="draft", to_state="sent", guards=[guard])],
    )
    return TransitionValidator(sm)


@pytest.mark.parametrize(
    ("user_roles", "ok"),
    [(["agent"], True), (["manager"], True), (["viewer"], False), ([], False)],
    ids=["first", "second", "other", "none"],
)
def test_any_of_role_guard_at_runtime(user_roles: list[str], ok: bool) -> None:
    guard = TransitionGuardSpec(requires_role="agent", requires_any_role=["agent", "manager"])
    result = _validator(guard).validate_transition("draft", "sent", {}, user_roles=user_roles)
    assert result.is_valid is ok
    if not ok:
        assert "'Agent' or 'Manager'" in str(result.error)


def test_transition_effects_wire_by_entity_and_warn_when_none(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from dazzle.http.runtime.service_generator import CRUDService
    from dazzle.http.runtime.subsystems.system_routes import SystemRoutesSubsystem

    class _Crud(CRUDService):  # minimal stand-in: isinstance + on_updated
        def __init__(self, entity_name: str) -> None:  # noqa: D401
            self.entity_name = entity_name
            self.callbacks: list = []

        def on_updated(self, cb) -> None:
            self.callbacks.append(cb)

    effect = SimpleNamespace()
    t = SimpleNamespace(from_state="a", to_state="b", effects=[effect])
    sm = SimpleNamespace(transitions=[t], status_field="status")
    entity = SimpleNamespace(name="Doc", state_machine=sm)
    svc = _Crud("Doc")
    ctx = SimpleNamespace(
        appspec=SimpleNamespace(domain=SimpleNamespace(entities=[entity])),
        entity_services={"Doc": svc},
    )
    with caplog.at_level(logging.WARNING):
        SystemRoutesSubsystem._init_transition_effects(
            SystemRoutesSubsystem.__new__(SystemRoutesSubsystem), ctx
        )
    assert len(svc.callbacks) == 1
    assert not [r for r in caplog.records if "NOT wired" in r.getMessage()]

    other = SimpleNamespace(name="Other", state_machine=sm)
    ctx.appspec.domain.entities = [other]
    with caplog.at_level(logging.WARNING):
        SystemRoutesSubsystem._init_transition_effects(
            SystemRoutesSubsystem.__new__(SystemRoutesSubsystem), ctx
        )
    assert [
        r for r in caplog.records if "NOT wired" in r.getMessage() and "Other" in r.getMessage()
    ]
