"""IR models for scene walks (#1638 PR1).

Mirrors CyFuture ``scene_walk.schema.json`` with a documented **core** action
set for framework PR1 and an extended set accepted for pilot YAML porting.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WalkActionType(StrEnum):
    """Action verbs for deterministic scene walks.

    **Core (PR1 / showcase):** navigate, assert_*, playwright_click, playwright_wait.
    **Extension (pilot / PR2+):** api_* helpers — valid in schema; runner maps later.
    """

    # Core
    NAVIGATE = "navigate"
    ASSERT_NOT_LOGIN = "assert_not_login"
    ASSERT_HTTP_OK = "assert_http_ok"
    ASSERT_HTTP_OK_OR_EMPTY = "assert_http_ok_or_empty"
    ASSERT_HTTP_OK_OR_FORBIDDEN = "assert_http_ok_or_forbidden"
    ASSERT_NO_SERVER_ERROR = "assert_no_server_error"
    ASSERT_NO_ERROR_BANNER = "assert_no_error_banner"
    ASSERT_ANY_TEXT = "assert_any_text"
    ASSERT_HAS_DZ_OR_CONTENT = "assert_has_dz_or_content"
    PLAYWRIGHT_CLICK = "playwright_click"
    PLAYWRIGHT_WAIT = "playwright_wait"
    # Extension (CyFuture pilot — do not block PR1 load/validate)
    API_FIND = "api_find"
    API_ENSURE_STATUS = "api_ensure_status"
    API_ASSERT_FIELD = "api_assert_field"
    API_POST = "api_post"
    API_UPLOAD_FILE = "api_upload_file"
    API_AGENT_ENSURE_EL_VIEWED = "api_agent_ensure_el_viewed"


CORE_ACTION_TYPES: frozenset[WalkActionType] = frozenset(
    {
        WalkActionType.NAVIGATE,
        WalkActionType.ASSERT_NOT_LOGIN,
        WalkActionType.ASSERT_HTTP_OK,
        WalkActionType.ASSERT_HTTP_OK_OR_EMPTY,
        WalkActionType.ASSERT_HTTP_OK_OR_FORBIDDEN,
        WalkActionType.ASSERT_NO_SERVER_ERROR,
        WalkActionType.ASSERT_NO_ERROR_BANNER,
        WalkActionType.ASSERT_ANY_TEXT,
        WalkActionType.ASSERT_HAS_DZ_OR_CONTENT,
        WalkActionType.PLAYWRIGHT_CLICK,
        WalkActionType.PLAYWRIGHT_WAIT,
    }
)


class ActionSpec(BaseModel):
    """One step in a scene."""

    model_config = ConfigDict(extra="allow")

    type: WalkActionType
    texts: list[str] | None = None
    entry: str | None = None
    path: str | None = None
    role: str | None = None
    name: str | None = None
    # Common extension fields (kept typed for golden YAML; extra=allow for rest)
    where: dict[str, Any] | None = None
    save_as: str | None = None
    id_var: str | None = None
    path_template: str | None = None
    status: str | None = None
    field: str | None = None
    equals: str | None = None
    wait_ms: int | None = None
    regex: bool | None = None
    api_fallback_status: str | None = None
    company_name_contains: str | None = None
    prefer_status: str | None = None

    @property
    def is_core(self) -> bool:
        return self.type in CORE_ACTION_TYPES


class SceneSpec(BaseModel):
    """One story-linked scene (multi-action path)."""

    model_config = ConfigDict(extra="allow")

    id: str
    actions: list[ActionSpec] = Field(min_length=1)
    story: str | None = None
    entry: str | None = None
    expects: str | None = None


class SceneWalkSpec(BaseModel):
    """Deterministic persona walk document (one YAML file)."""

    model_config = ConfigDict(extra="allow")

    persona: str
    scenes: list[SceneSpec] = Field(min_length=1)
    email_env: str | None = None
    password_env: str | None = None
    rhythm: str | None = None
    phase: str | None = None
    home_workspace: str | None = None

    # Filled by loader (not in YAML)
    walk_id: str | None = Field(default=None, exclude=True)
    source_path: str | None = Field(default=None, exclude=True)

    def core_only(self) -> bool:
        """True when every action is in the PR1 core set."""
        return all(a.is_core for s in self.scenes for a in s.actions)

    def story_ids(self) -> list[str]:
        return sorted({s.story for s in self.scenes if s.story})
