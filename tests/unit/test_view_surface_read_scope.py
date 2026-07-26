"""VIEW surfaces require a READ scope when the entity declares scopes at all.

Fleet dig (2026-07-26): project_tracker Task had list scopes but no read —
queue drills linked to detail which fail-closed as 404 not_found. Guard the
pattern across all example apps.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.ir import PermissionKind, SurfaceMode

_REPO = Path(__file__).resolve().parents[2]
_EXAMPLES = _REPO / "examples"


def _example_apps() -> list[str]:
    return sorted(
        p.name for p in _EXAMPLES.iterdir() if p.is_dir() and (p / "dazzle.toml").is_file()
    )


def _scope_ops(entity) -> set[str]:
    access = getattr(entity, "access", None)
    if access is None or not getattr(access, "scopes", None):
        return set()
    out: set[str] = set()
    for sc in access.scopes:
        op = sc.operation
        out.add(op.value if hasattr(op, "value") else str(op))
    return out


@pytest.mark.parametrize("app", _example_apps())
def test_view_surface_entity_has_read_scope_when_scoped(app: str) -> None:
    """If an entity has any scope rules and a VIEW surface, it must include read."""
    spec = load_project_appspec(_EXAMPLES / app)
    ent_ops = {e.name: _scope_ops(e) for e in spec.domain.entities}
    offenders: list[str] = []
    for s in spec.surfaces:
        mode = getattr(s.mode, "value", s.mode)
        if mode != SurfaceMode.VIEW and mode != "view":
            continue
        ent = s.entity_ref
        if not ent:
            continue
        ops = ent_ops.get(ent, set())
        if not ops:
            continue  # no scopes at all — different posture
        if "list" in ops and "read" not in ops:
            offenders.append(f"{s.name} (entity {ent}) has list scope but no read")
        elif "read" not in ops and ops:
            # any scopes without read is still broken for detail
            offenders.append(f"{s.name} (entity {ent}) has scopes {sorted(ops)} but no read")
    assert not offenders, f"{app}: VIEW surfaces missing entity READ scope:\n  " + "\n  ".join(
        offenders
    )


def test_permission_kind_read_value() -> None:
    assert PermissionKind.READ.value == "read"
