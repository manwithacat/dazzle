"""Walk run result types and path templating (#1638 / #1639)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActionResult:
    """Outcome of one walk action."""

    type: str
    ok: bool
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class SceneResult:
    """Outcome of one scene."""

    scene_id: str
    ok: bool
    story: str | None = None
    actions: list[ActionResult] = field(default_factory=list)
    error: str | None = None


@dataclass
class WalkRunResult:
    """Outcome of a full walk run."""

    walk_id: str
    persona: str
    ok: bool
    dry_run: bool = False
    base_url: str = ""
    scenes: list[SceneResult] = field(default_factory=list)
    error: str | None = None

    def summary(self) -> str:
        mode = "dry-run" if self.dry_run else "run"
        status = "PASS" if self.ok else "FAIL"
        n_ok = sum(1 for s in self.scenes if s.ok)
        return (
            f"{status} [{mode}] walk={self.walk_id} persona={self.persona} "
            f"scenes={n_ok}/{len(self.scenes)}" + (f" error={self.error}" if self.error else "")
        )


def render_template(template: str | None, vars_: dict[str, str]) -> str:
    """Replace ``{var}`` placeholders from prior ``save_as`` values."""
    if not template:
        return ""
    out = template
    for key, val in vars_.items():
        out = out.replace("{" + key + "}", val)
    return out
