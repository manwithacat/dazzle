"""Validate loaded walks against optional AppSpec context (#1638 PR1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from dazzle.core.ir.identity import spec_display_id
from dazzle.testing.walk.loader import WalkLoadError, load_walk
from dazzle.testing.walk.models import CORE_ACTION_TYPES, SceneWalkSpec

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec


@dataclass(frozen=True)
class WalkValidationIssue:
    """One validation finding for a walk file."""

    path: str
    walk_id: str | None
    level: str  # "error" | "warning"
    code: str
    message: str

    def format(self) -> str:
        loc = self.walk_id or Path(self.path).stem
        return f"{self.level.upper()} [{self.code}] {loc}: {self.message}"


def _issue(
    path: str,
    wid: str | None,
    level: str,
    code: str,
    message: str,
) -> WalkValidationIssue:
    return WalkValidationIssue(path, wid, level, code, message)


def _check_actions(
    walk: SceneWalkSpec,
    path: str,
    wid: str | None,
    *,
    require_core_only: bool,
) -> list[WalkValidationIssue]:
    issues: list[WalkValidationIssue] = []
    for scene in walk.scenes:
        for action in scene.actions:
            if action.type in CORE_ACTION_TYPES:
                continue
            level = "error" if require_core_only else "warning"
            msg = (
                f"scene {scene.id!r}: action {action.type.value!r} is extension "
                "(not in PR1 core set); use core verbs for showcase walks"
                if require_core_only
                else (
                    f"scene {scene.id!r}: extension action {action.type.value!r} "
                    "(ok for pilot; runner support lands in PR2+)"
                )
            )
            issues.append(_issue(path, wid, level, "extension_action", msg))
    return issues


def _check_stories(
    walk: SceneWalkSpec,
    path: str,
    wid: str | None,
    *,
    require_story: bool,
) -> list[WalkValidationIssue]:
    issues: list[WalkValidationIssue] = []
    for scene in walk.scenes:
        if not scene.id.strip():
            issues.append(
                _issue(path, wid, "error", "empty_scene_id", "scene id must be non-empty")
            )
        if scene.story:
            continue
        if require_story:
            issues.append(
                _issue(
                    path,
                    wid,
                    "error",
                    "story_required",
                    f"scene {scene.id!r} missing story: (required for verified claims)",
                )
            )
        else:
            issues.append(
                _issue(
                    path,
                    wid,
                    "warning",
                    "story_missing",
                    f"scene {scene.id!r} has no story: binding preferred for job QA",
                )
            )
    return issues


def _appspec_ids(appspec: AppSpec) -> tuple[set[str], set[str], set[str]]:
    """Return (persona_ids, story_ids, workspace_names)."""
    personas = {
        pid
        for p in (appspec.personas or [])
        if (pid := spec_display_id(p, default=None, prefer="id")) is not None
    }
    # StorySpec identity is ``story_id`` (not the name/id footgun pair).
    stories = {s.story_id for s in (appspec.stories or []) if s.story_id}
    workspaces = {w.name for w in (appspec.workspaces or [])}
    return personas, stories, workspaces


def _check_appspec(
    walk: SceneWalkSpec,
    path: str,
    wid: str | None,
    appspec: AppSpec,
) -> list[WalkValidationIssue]:
    issues: list[WalkValidationIssue] = []
    persona_ids, story_ids, ws_names = _appspec_ids(appspec)
    if walk.persona and walk.persona not in persona_ids:
        issues.append(
            _issue(
                path,
                wid,
                "error",
                "unknown_persona",
                f"persona {walk.persona!r} not in AppSpec personas "
                f"({', '.join(sorted(persona_ids)) or 'none'})",
            )
        )
    if walk.home_workspace and walk.home_workspace not in ws_names:
        issues.append(
            _issue(
                path,
                wid,
                "warning",
                "unknown_workspace",
                f"home_workspace {walk.home_workspace!r} not in AppSpec workspaces",
            )
        )
    for sid in walk.story_ids():
        if story_ids and sid not in story_ids:
            issues.append(
                _issue(path, wid, "error", "unknown_story", f"story {sid!r} not in AppSpec stories")
            )
    return issues


def validate_walk(
    walk: SceneWalkSpec,
    *,
    appspec: AppSpec | None = None,
    require_core_only: bool = False,
    require_story: bool = False,
) -> list[WalkValidationIssue]:
    """Return issues for a loaded walk (empty = clean)."""
    path = walk.source_path or "<memory>"
    wid = walk.walk_id
    issues: list[WalkValidationIssue] = []

    if not walk.persona.strip():
        issues.append(_issue(path, wid, "error", "empty_persona", "persona must be non-empty"))

    issues.extend(_check_stories(walk, path, wid, require_story=require_story))
    issues.extend(_check_actions(walk, path, wid, require_core_only=require_core_only))
    if appspec is not None:
        issues.extend(_check_appspec(walk, path, wid, appspec))
    return issues


def validate_walks(
    paths: list[Path],
    *,
    appspec: AppSpec | None = None,
    require_core_only: bool = False,
    require_story: bool = False,
) -> tuple[list[SceneWalkSpec], list[WalkValidationIssue]]:
    """Load each path and collect validation issues (load failures → errors)."""
    walks: list[SceneWalkSpec] = []
    issues: list[WalkValidationIssue] = []
    for p in paths:
        try:
            walk = load_walk(p)
        except WalkLoadError as e:
            issues.append(WalkValidationIssue(str(p), Path(p).stem, "error", "load_failed", str(e)))
            continue
        walks.append(walk)
        issues.extend(
            validate_walk(
                walk,
                appspec=appspec,
                require_core_only=require_core_only,
                require_story=require_story,
            )
        )
    return walks, issues
