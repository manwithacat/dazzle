"""Job claim registry — docs maturity SSOT (#1638 PR3).

Separate from ``dazzle.rbac.claim_ledger`` (access-copy / proof model).
Here each *guide* claims a user-facing job is at a lifecycle status, bound
to stories + optional deterministic scene walk.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from dazzle.core.ir.identity import spec_display_id
from dazzle.testing.walk.discovery import default_walks_dir, discover_walk_paths
from dazzle.testing.walk.loader import WalkLoadError, load_walk
from dazzle.testing.walk.runner import run_walk_sync
from dazzle.testing.walk.validate import validate_walk

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec
    from dazzle.testing.walk.models import SceneWalkSpec

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

# Statuses that require a walk file (and, with --run, a green walk).
WALK_REQUIRED_STATUSES = frozenset({"verified", "sensible", "filmed", "evergreen"})


class ClaimStatus(StrEnum):
    """Lifecycle from CyFuture maturity / #1638 design."""

    DRAFT = "draft"
    DOCUMENTED = "documented"
    VERIFIED = "verified"
    SENSIBLE = "sensible"
    FILMED = "filmed"
    EVERGREEN = "evergreen"


class ClaimGuide(BaseModel):
    """One user-facing job claim row."""

    model_config = ConfigDict(extra="allow")

    id: str
    path: str
    persona: str
    status: ClaimStatus
    job_id: str | None = None
    title: str | None = None
    stories: list[str] = Field(default_factory=list)
    walk: str | None = None
    pack: str | int | None = None
    pack_tier: str | None = None
    video: str | None = None
    notes: str | None = None


class JobClaimRegistry(BaseModel):
    """Root registry document (YAML)."""

    model_config = ConfigDict(extra="allow")

    version: int = Field(ge=1)
    guides: list[ClaimGuide] = Field(default_factory=list)
    base_url_default: str | None = None
    video_dir: str | None = None
    trace_dir: str | None = None
    planned: list[dict[str, Any]] = Field(default_factory=list)

    source_path: str | None = Field(default=None, exclude=True)


class ClaimsLoadError(ValueError):
    """Registry missing or invalid."""

    def __init__(self, path: Path | str, message: str) -> None:
        self.path = Path(path)
        super().__init__(f"{self.path}: {message}")


DEFAULT_REGISTRY_CANDIDATES = (
    Path("fixtures") / "job_claims.yaml",
    Path("docs") / "job_claims.yaml",
    Path("docs") / "internal" / "maturity.yaml",
)


def discover_registry_path(project_root: Path, explicit: Path | None = None) -> Path | None:
    """Return first existing registry path under *project_root*."""
    if explicit is not None:
        p = explicit if explicit.is_absolute() else project_root / explicit
        return p if p.is_file() else None
    for rel in DEFAULT_REGISTRY_CANDIDATES:
        cand = project_root / rel
        if cand.is_file():
            return cand
    return None


def load_registry(path: Path | str) -> JobClaimRegistry:
    """Load and validate a job claim registry YAML."""
    p = Path(path).resolve()
    if not p.is_file():
        raise ClaimsLoadError(p, "file not found")
    if yaml is None:
        raise ClaimsLoadError(p, "PyYAML required")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ClaimsLoadError(p, f"YAML parse error: {e}") from e
    if not isinstance(data, dict):
        raise ClaimsLoadError(p, "expected mapping at root")
    try:
        reg = JobClaimRegistry.model_validate(data)
    except Exception as e:
        raise ClaimsLoadError(p, f"schema validation failed: {e}") from e
    reg.source_path = str(p)
    return reg


@dataclass(frozen=True)
class ClaimIssue:
    """One claims-check finding."""

    guide_id: str
    level: str  # error | warning
    code: str
    message: str

    def format(self) -> str:
        return f"{self.level.upper()} [{self.code}] {self.guide_id}: {self.message}"


@dataclass
class ClaimsCheckResult:
    """Aggregate result of ``claims check``."""

    registry_path: str
    guides: int
    issues: list[ClaimIssue]
    walk_results: dict[str, bool] | None = None

    def __post_init__(self) -> None:
        if self.walk_results is None:
            self.walk_results = {}

    @property
    def errors(self) -> list[ClaimIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ClaimIssue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


def _walk_file(project_root: Path, walk_id: str) -> Path | None:
    for p in discover_walk_paths(project_root):
        if p.stem == walk_id:
            return p
    cand = default_walks_dir(project_root) / f"{walk_id}.yaml"
    return cand if cand.is_file() else None


def _appspec_ids(appspec: AppSpec) -> tuple[set[str], set[str]]:
    personas = {
        pid
        for p in (appspec.personas or [])
        if (pid := spec_display_id(p, default=None, prefer="id")) is not None
    }
    stories = {s.story_id for s in (appspec.stories or []) if s.story_id}
    return personas, stories


def _check_doc_path(guide: ClaimGuide, root: Path) -> ClaimIssue | None:
    if guide.status == ClaimStatus.DRAFT:
        return None
    if (root / guide.path).is_file():
        return None
    level = "error" if guide.status.value in WALK_REQUIRED_STATUSES else "warning"
    return ClaimIssue(
        guide.id,
        level,
        "missing_doc",
        f"path {guide.path!r} not found under project root",
    )


def _check_persona_stories(
    guide: ClaimGuide,
    persona_ids: set[str],
    story_ids: set[str],
    *,
    has_appspec: bool,
) -> list[ClaimIssue]:
    issues: list[ClaimIssue] = []
    if has_appspec and guide.persona not in persona_ids:
        issues.append(
            ClaimIssue(
                guide.id,
                "error",
                "unknown_persona",
                f"persona {guide.persona!r} not in AppSpec",
            )
        )
    for sid in guide.stories:
        if story_ids and sid not in story_ids:
            issues.append(
                ClaimIssue(
                    guide.id,
                    "error",
                    "unknown_story",
                    f"story {sid!r} not in AppSpec",
                )
            )
    return issues


def _load_guide_walk(
    guide: ClaimGuide,
    root: Path,
    needs_walk: bool,
) -> tuple[SceneWalkSpec | None, list[ClaimIssue]]:
    """Resolve walk binding; return (walk or None, issues)."""
    issues: list[ClaimIssue] = []
    if needs_walk and not guide.walk:
        issues.append(
            ClaimIssue(
                guide.id,
                "error",
                "walk_required",
                f"status {guide.status.value!r} requires walk: binding",
            )
        )
        return None, issues
    if not guide.walk:
        if guide.status == ClaimStatus.DOCUMENTED:
            issues.append(
                ClaimIssue(
                    guide.id,
                    "warning",
                    "no_walk",
                    "documented claim has no walk yet (cannot promote to verified)",
                )
            )
        return None, issues

    walk_path = _walk_file(root, guide.walk)
    if walk_path is None:
        issues.append(
            ClaimIssue(
                guide.id,
                "error",
                "missing_walk",
                f"walk {guide.walk!r} not found under fixtures/scene_walks/",
            )
        )
        return None, issues
    try:
        return load_walk(walk_path), issues
    except WalkLoadError as e:
        issues.append(ClaimIssue(guide.id, "error", "walk_load", str(e)))
        return None, issues


def _check_walk_alignment(
    guide: ClaimGuide,
    walk: SceneWalkSpec,
    *,
    needs_walk: bool,
    appspec: AppSpec | None,
) -> list[ClaimIssue]:
    issues: list[ClaimIssue] = []
    for vi in validate_walk(walk, appspec=appspec, require_story=needs_walk):
        if vi.level == "error":
            issues.append(ClaimIssue(guide.id, "error", f"walk_{vi.code}", vi.message))
    if walk.persona and walk.persona != guide.persona:
        issues.append(
            ClaimIssue(
                guide.id,
                "warning",
                "persona_mismatch",
                f"guide persona {guide.persona!r} != walk persona {walk.persona!r}",
            )
        )
    for sid in guide.stories:
        if sid not in walk.story_ids() and needs_walk:
            issues.append(
                ClaimIssue(
                    guide.id,
                    "warning",
                    "story_not_in_walk",
                    f"claim story {sid!r} not referenced in walk scenes",
                )
            )
    return issues


def _maybe_run_walk(
    guide: ClaimGuide,
    walk: SceneWalkSpec,
    *,
    root: Path,
    base_url: str | None,
    registry: JobClaimRegistry,
) -> tuple[bool, ClaimIssue | None]:
    url = base_url or registry.base_url_default or "http://127.0.0.1:8000"
    result = run_walk_sync(walk, base_url=url, project_root=root, dry_run=False)
    if result.ok:
        return True, None
    return False, ClaimIssue(
        guide.id,
        "error",
        "walk_failed",
        result.error or f"walk {guide.walk!r} failed",
    )


def _check_one_guide(
    guide: ClaimGuide,
    *,
    root: Path,
    persona_ids: set[str],
    story_ids: set[str],
    appspec: AppSpec | None,
    run_walks: bool,
    base_url: str | None,
    registry: JobClaimRegistry,
    walk_results: dict[str, bool],
) -> list[ClaimIssue]:
    issues: list[ClaimIssue] = []
    doc_issue = _check_doc_path(guide, root)
    if doc_issue:
        issues.append(doc_issue)
    issues.extend(
        _check_persona_stories(
            guide,
            persona_ids,
            story_ids,
            has_appspec=appspec is not None,
        )
    )
    needs_walk = guide.status.value in WALK_REQUIRED_STATUSES
    walk, walk_issues = _load_guide_walk(guide, root, needs_walk)
    issues.extend(walk_issues)
    if walk is None:
        return issues
    issues.extend(_check_walk_alignment(guide, walk, needs_walk=needs_walk, appspec=appspec))
    if run_walks and needs_walk and guide.walk:
        ok, fail = _maybe_run_walk(guide, walk, root=root, base_url=base_url, registry=registry)
        walk_results[guide.walk] = ok
        if fail:
            issues.append(fail)
    return issues


def check_registry(
    registry: JobClaimRegistry,
    *,
    project_root: Path,
    appspec: AppSpec | None = None,
    run_walks: bool = False,
    base_url: str | None = None,
) -> ClaimsCheckResult:
    """Validate claim rows against docs paths, walks, and optional live run."""
    root = project_root.resolve()
    issues: list[ClaimIssue] = []
    walk_results: dict[str, bool] = {}
    persona_ids: set[str] = set()
    story_ids: set[str] = set()
    if appspec is not None:
        persona_ids, story_ids = _appspec_ids(appspec)

    seen: set[str] = set()
    for guide in registry.guides:
        if guide.id in seen:
            issues.append(
                ClaimIssue(guide.id, "error", "duplicate_id", f"duplicate guide id {guide.id!r}")
            )
            continue
        seen.add(guide.id)
        issues.extend(
            _check_one_guide(
                guide,
                root=root,
                persona_ids=persona_ids,
                story_ids=story_ids,
                appspec=appspec,
                run_walks=run_walks,
                base_url=base_url,
                registry=registry,
                walk_results=walk_results,
            )
        )

    return ClaimsCheckResult(
        registry_path=registry.source_path or "<memory>",
        guides=len(registry.guides),
        issues=issues,
        walk_results=walk_results,
    )
