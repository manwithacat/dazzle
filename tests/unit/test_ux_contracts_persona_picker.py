"""Tests for the workspace contract persona picker.

Pins the decision tree documented on `_pick_workspace_check_persona`:
  1. Explicit `access: persona(...)` on the workspace wins.
  2. Else, a persona whose `default_workspace` points at the workspace.
  3. Else, the first declared persona (admin by convention).

This was reported as a real issue when `dazzle ux verify --contracts`
on support_tickets returned three false-positive 403s because the
picker skipped step 2 and defaulted to admin on workspaces that
agent / manager / customer actually own.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from dazzle.cli.ux import _pick_workspace_check_persona


@dataclass
class _Persona:
    id: str
    default_workspace: str | None = None


@dataclass
class _Access:
    allow_personas: list[str] = field(default_factory=list)


@dataclass
class _Workspace:
    name: str
    access: _Access | None = None


@dataclass
class _AppSpec:
    workspaces: list[_Workspace]
    personas: list[_Persona]


_W_QUEUE_MANAGER = _Workspace(name="queue", access=_Access(allow_personas=["manager"]))
_W_QUEUE_OPEN = _Workspace(name="queue", access=None)
_W_ORPHAN = _Workspace(name="orphan", access=None)
_W_QUEUE_EMPTY_ACCESS = _Workspace(name="queue", access=_Access(allow_personas=[]))
_W_X = _Workspace(name="x", access=None)


@pytest.mark.parametrize(
    ("workspaces", "personas", "target", "expected"),
    [
        (
            [_W_QUEUE_MANAGER],
            [
                _Persona(id="admin"),
                _Persona(id="manager"),
                _Persona(id="agent", default_workspace="queue"),
            ],
            "queue",
            "manager",
        ),
        (
            [_W_QUEUE_OPEN],
            [
                _Persona(id="admin", default_workspace="_platform_admin"),
                _Persona(id="customer", default_workspace="my_tickets"),
                _Persona(id="agent", default_workspace="queue"),
                _Persona(id="manager", default_workspace="dashboard"),
            ],
            "queue",
            "agent",
        ),
        (
            [_W_ORPHAN],
            [
                _Persona(id="admin"),
                _Persona(id="customer", default_workspace="somewhere_else"),
            ],
            "orphan",
            "admin",
        ),
        (
            [_W_QUEUE_EMPTY_ACCESS],
            [
                _Persona(id="admin"),
                _Persona(id="agent", default_workspace="queue"),
            ],
            "queue",
            "agent",
        ),
        ([_W_X], [], "x", "admin"),
    ],
    ids=[
        "test_explicit_access_block_wins",
        "test_default_workspace_reverse_lookup",
        "test_fallback_to_first_persona_when_nothing_matches",
        "test_empty_access_allow_personas_falls_through",
        "test_no_personas_at_all_defaults_to_admin_literal",
    ],
)
def test_pick_workspace_check_persona(
    workspaces: list[_Workspace],
    personas: list[_Persona],
    target: str,
    expected: str,
) -> None:
    spec = _AppSpec(workspaces=workspaces, personas=personas)
    assert _pick_workspace_check_persona(spec, target) == expected
