"""Discover example apps under examples/."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Align with demo_fleet / story_walk showcase when --showcase-only
SHOWCASE = (
    "simple_task",
    "support_tickets",
    "invoice_ops",
    "contact_manager",
    "ops_dashboard",
    "project_tracker",
    "design_studio",
    "hr_records",
    "fieldtest_hub",
)

_APP_SLUG = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ExampleApp:
    """One example project with a dazzle.toml."""

    name: str
    path: Path
    title: str
    has_spec: bool
    has_trial: bool
    has_stories: bool
    port: int

    @property
    def host(self) -> str:
        return f"{self.name}.dazzle.local"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def examples_root(root: Path | None = None) -> Path:
    return (root or repo_root()) / "examples"


def _title_from_toml(toml_path: Path, fallback: str) -> str:
    try:
        text = toml_path.read_text(encoding="utf-8")
    except OSError:
        return fallback
    # light parse — avoid requiring tomllib shape
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("name") and "=" in line:
            raw = line.split("=", 1)[1].strip().strip("\"'")
            if raw:
                return raw
        if line.startswith("title") and "=" in line:
            raw = line.split("=", 1)[1].strip().strip("\"'")
            if raw:
                return raw
    return fallback.replace("_", " ").title()


def discover_apps(
    *,
    root: Path | None = None,
    showcase_only: bool = False,
    backend_base: int = 9100,
) -> list[ExampleApp]:
    """Return sorted example apps with stable port assignment."""
    ex = examples_root(root)
    if not ex.is_dir():
        return []
    names: list[str] = []
    for p in sorted(ex.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue
        if not (p / "dazzle.toml").is_file():
            continue
        if not _APP_SLUG.match(p.name):
            continue
        if showcase_only and p.name not in SHOWCASE:
            continue
        names.append(p.name)

    # stable order: showcase order first, then alpha remainder
    if not showcase_only:
        ordered = [n for n in SHOWCASE if n in names]
        ordered += sorted(n for n in names if n not in SHOWCASE)
        names = ordered
    else:
        names = [n for n in SHOWCASE if n in names]

    apps: list[ExampleApp] = []
    for i, name in enumerate(names):
        path = ex / name
        toml = path / "dazzle.toml"
        apps.append(
            ExampleApp(
                name=name,
                path=path,
                title=_title_from_toml(toml, name),
                has_spec=(path / "SPECIFICATION.md").is_file() or (path / "SPEC.md").is_file(),
                has_trial=(path / "trial.toml").is_file(),
                has_stories=any((path / "dsl").rglob("stories.dsl"))
                if (path / "dsl").is_dir()
                else False,
                port=backend_base + i,
            )
        )
    return apps


def app_by_name(name: str, apps: list[ExampleApp]) -> ExampleApp | None:
    key = name.lower().strip()
    for a in apps:
        if a.name == key:
            return a
    return None


def parse_host(host_header: str | None, *, hub_domain: str = "dazzle.local") -> str | None:
    """Return app slug for ``{app}.dazzle.local``, or None for hub hosts.

    Unknown subdomains return the string ``?unknown:<slug>``.
    """
    if not host_header:
        return None
    host = host_header.split(":", 1)[0].strip().lower()
    if not host or host in ("localhost", "127.0.0.1", "::1"):
        return None
    hub = hub_domain.lower()
    if host in (hub, f"www.{hub}", f"hub.{hub}"):
        return None
    suffix = f".{hub}"
    if host.endswith(suffix):
        slug = host[: -len(suffix)]
        if not slug or "." in slug:
            return f"?unknown:{slug or host}"
        if not _APP_SLUG.match(slug):
            return f"?unknown:{slug}"
        return slug
    # bare IP / other host → hub
    return None
