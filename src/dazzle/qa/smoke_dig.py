"""Fleet L2.5 dig: cycle showcase apps with a random seed order.

Shortcut for agent_qa_smoke across the fleet::

    dazzle qa smoke-dig              # one app, random seed rotation
    dazzle qa smoke-dig --all        # full cycle
    dazzle qa smoke-dig --seed 42 --all
    python scripts/qa_smoke_dig.py --once

Order = shuffle(SHOWCASE, seed). Cursor advances in ``.dazzle/qa-smoke-dig-state.json``
so successive ``--once`` calls walk the fleet without redoing the same app first.
"""

from __future__ import annotations

import json
import logging
import random
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

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

STATE_REL = ".dazzle/qa-smoke-dig-state.json"
HUB_API = "http://127.0.0.1:9080/_hub"
DEFAULT_BACKEND_BASE = 9100
DEFAULT_PERSONA = "manager"


@dataclass
class DigAppResult:
    app: str
    base_url: str
    persona: str
    ok: bool
    smoke_auto_seed: int = 0
    coverage_ok: bool | None = None
    detail: str = ""
    report_path: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DigState:
    seed: int = 0
    order: list[str] = field(default_factory=list)
    cursor: int = 0
    last_app: str = ""
    last_at: str = ""
    completed: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DigState:
        return cls(
            seed=int(data.get("seed") or 0),
            order=list(data.get("order") or []),
            cursor=int(data.get("cursor") or 0),
            last_app=str(data.get("last_app") or ""),
            last_at=str(data.get("last_at") or ""),
            completed=list(data.get("completed") or []),
        )


def repo_root() -> Path:
    # src/dazzle/qa/smoke_dig.py → parents[3] = monorepo root (not parents[2]=src/)
    return Path(__file__).resolve().parents[3]


def state_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / STATE_REL


def load_state(root: Path | None = None) -> DigState | None:
    path = state_path(root)
    if not path.is_file():
        return None
    try:
        return DigState.from_json(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def save_state(state: DigState, root: Path | None = None) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_json(), indent=2) + "\n", encoding="utf-8")


def shuffle_order(apps: list[str], seed: int) -> list[str]:
    order = list(apps)
    random.Random(seed).shuffle(order)
    return order


def new_state(*, seed: int | None = None, apps: list[str] | None = None) -> DigState:
    s = int(seed if seed is not None else random.randint(1, 2**31 - 1))
    apps = list(apps or SHOWCASE)
    return DigState(seed=s, order=shuffle_order(apps, s), cursor=0)


def resolve_order(
    *,
    seed: int | None = None,
    resume: bool = True,
    apps: list[str] | None = None,
    root: Path | None = None,
) -> DigState:
    """Build or resume rotation state."""
    root = root or repo_root()
    apps = list(apps or showcase_apps(root))
    if resume and seed is None:
        prev = load_state(root)
        if prev and prev.order:
            # Drop apps no longer present; keep seed/cursor when possible.
            prev.order = [a for a in prev.order if a in apps] + [
                a for a in apps if a not in prev.order
            ]
            return prev
    return new_state(seed=seed, apps=apps)


def showcase_apps(root: Path | None = None) -> list[str]:
    root = root or repo_root()
    ex = root / "examples"
    return [a for a in SHOWCASE if (ex / a / "dazzle.toml").is_file()]


def persona_for_app(app: str, root: Path | None = None) -> str:
    """First trial.toml login_persona, else manager."""
    root = root or repo_root()
    trial = root / "examples" / app / "trial.toml"
    if not trial.is_file():
        return DEFAULT_PERSONA
    try:
        text = trial.read_text(encoding="utf-8")
    except OSError:
        return DEFAULT_PERSONA
    m = re.search(r'login_persona\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1) if m else DEFAULT_PERSONA


def port_for_app(app: str, root: Path | None = None) -> int:
    """Stable hub port: showcase index from 9100, else hash-ish from name order."""
    root = root or repo_root()
    try:
        sys.path.insert(0, str(root / "scripts" / "example_hub"))
        from registry import discover_apps

        for a in discover_apps(root=root, showcase_only=False):
            if a.name == app:
                return int(a.port)
    except (ImportError, OSError, AttributeError, TypeError, ValueError):
        logger.debug("registry port lookup failed for %s", app, exc_info=True)
    if app in SHOWCASE:
        return DEFAULT_BACKEND_BASE + SHOWCASE.index(app)
    return DEFAULT_BACKEND_BASE + 50 + (sum(ord(c) for c in app) % 40)


def base_url_for_app(app: str, root: Path | None = None) -> str:
    return f"http://127.0.0.1:{port_for_app(app, root)}"


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_health(base_url: str, *, timeout_s: float = 20.0) -> bool:
    deadline = time.time() + timeout_s
    url = base_url.rstrip("/") + "/"
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if 200 <= getattr(resp, "status", 200) < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.4)
    return False


def hub_start_app(app: str, *, hub_api: str = HUB_API) -> bool:
    """POST /_hub/start/{app} — best-effort; returns True if request accepted."""
    url = hub_api.rstrip("/") + f"/start/{app}"
    try:
        req = urllib.request.Request(url, method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            return 200 <= getattr(resp, "status", 200) < 400
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.debug("hub start %s failed: %s", app, exc)
        return False


def ensure_running(
    app: str,
    base_url: str,
    *,
    timeout_s: float = 25.0,
    hub_api: str = HUB_API,
) -> bool:
    port = int(urlparse_port(base_url) or 0)
    if port and port_open(port):
        return wait_health(base_url, timeout_s=min(8.0, timeout_s))
    hub_start_app(app, hub_api=hub_api)
    # Also try direct serve if hub didn't bring it up (caller may have started it).
    return wait_health(base_url, timeout_s=timeout_s)


def urlparse_port(base_url: str) -> int | None:
    try:
        p = urlparse(base_url)
        if p.port:
            return int(p.port)
    except (ValueError, TypeError):
        return None
    return None


def _dazzle_bin(root: Path | None = None) -> str:
    root = root or repo_root()
    cand = root / ".venv" / "bin" / "dazzle"
    return str(cand) if cand.is_file() else "dazzle"


def _run_dazzle(
    args: list[str], *, root: Path | None = None, timeout: float = 300.0
) -> subprocess.CompletedProcess[str]:
    root = root or repo_root()
    cmd = [_dazzle_bin(root), *args]
    return subprocess.run(
        cmd,
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _newest_report(app_dir: Path, pattern: str) -> Path | None:
    files = sorted(app_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _auto_seed_count(path: Path | None) -> int:
    if path is None or not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    seed = data.get("auto_seed") or []
    return len(seed) if isinstance(seed, list) else 0


def dig_one(
    app: str,
    *,
    root: Path | None = None,
    base_url: str | None = None,
    persona: str | None = None,
    headless: bool = True,
    max_clicks: int = 12,
    fail_on_product: bool = False,
    run_coverage: bool = True,
    timeout_s: float = 25.0,
) -> DigAppResult:
    """Run L2.5 dig instruments for one app."""
    root = root or repo_root()
    base = (base_url or base_url_for_app(app, root)).rstrip("/")
    persona = persona or persona_for_app(app, root)
    result = DigAppResult(app=app, base_url=base, persona=persona, ok=True)

    if not ensure_running(app, base, timeout_s=timeout_s):
        # Fall back: try starting with local serve is out of scope for dig_one;
        # report harness failure so the campaign keeps walking.
        result.ok = False
        result.detail = f"app not healthy at {base} (try hub start or dazzle serve)"
        return result

    app_dir = root / "examples" / app
    if run_coverage:
        cov = _run_dazzle(
            [
                "qa",
                "trial-coverage",
                "-a",
                app,
                "-p",
                persona,
                "-u",
                base,
            ],
            root=root,
            timeout=120.0,
        )
        result.coverage_ok = cov.returncode == 0
        if cov.returncode != 0:
            logger.warning("trial-coverage %s exit %s: %s", app, cov.returncode, cov.stderr[:200])

    smoke_args = [
        "qa",
        "smoke-crawl",
        "-a",
        app,
        "-p",
        persona,
        "-u",
        base,
        "--max-clicks",
        str(max_clicks),
    ]
    if headless:
        smoke_args.append("--headless")
    else:
        smoke_args.append("--headed")
    if fail_on_product:
        smoke_args.append("--fail-on-product")

    smoke = _run_dazzle(smoke_args, root=root, timeout=360.0)
    report = _newest_report(app_dir / "dev_docs", "qa-smoke-*.json")
    result.report_path = str(report) if report else ""
    result.smoke_auto_seed = _auto_seed_count(report)
    if smoke.returncode != 0:
        result.ok = False
        result.detail = (
            f"smoke-crawl exit {smoke.returncode}: {(smoke.stderr or smoke.stdout)[:300]}"
        )
    elif result.smoke_auto_seed:
        result.ok = False
        result.detail = f"auto_seed remaining smoke={result.smoke_auto_seed}"
    else:
        result.detail = "ok"
        # Prefer stdout summary line
        for line in (smoke.stdout or "").splitlines():
            if "Smoke crawl" in line or "auto_seed=" in line:
                result.detail = line.strip()
                break
    return result


def dig_cycle(
    *,
    app: str | None = None,
    all_apps: bool = False,
    seed: int | None = None,
    max_clicks: int = 12,
    headless: bool = True,
    fail_on_product: bool = False,
    run_coverage: bool = True,
    root: Path | None = None,
) -> list[DigAppResult]:
    """Run dig for one app or a slice of the shuffled fleet."""
    root = root or repo_root()
    apps = showcase_apps(root)
    if not apps:
        raise RuntimeError("no showcase apps found")

    results: list[DigAppResult] = []
    if app:
        r = dig_one(
            app,
            root=root,
            headless=headless,
            max_clicks=max_clicks,
            fail_on_product=fail_on_product,
            run_coverage=run_coverage,
        )
        results.append(r)
        print(
            f"[smoke-dig] {r.app}: ok={r.ok} auto_seed={r.smoke_auto_seed} {r.detail}", flush=True
        )
        return results

    state = resolve_order(seed=seed, resume=True, apps=apps, root=root)
    if all_apps:
        to_run = list(state.order)
        state.cursor = 0
    else:
        if state.cursor >= len(state.order):
            state.cursor = 0
            state.completed = []
        to_run = [state.order[state.cursor]]
        state.cursor = (state.cursor + 1) % max(len(state.order), 1)

    for name in to_run:
        r = dig_one(
            name,
            root=root,
            headless=headless,
            max_clicks=max_clicks,
            fail_on_product=fail_on_product,
            run_coverage=run_coverage,
        )
        results.append(r)
        state.last_app = name
        state.last_at = datetime.now(UTC).isoformat()
        if name not in state.completed:
            state.completed.append(name)
        print(
            f"[smoke-dig] {r.app}: ok={r.ok} auto_seed={r.smoke_auto_seed} {r.detail}",
            flush=True,
        )
        save_state(state, root)

    # Fleet summary artifact
    out_dir = root / ".dazzle"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "seed": state.seed,
        "order": state.order,
        "cursor": state.cursor,
        "results": [r.to_json() for r in results],
        "at": datetime.now(UTC).isoformat(),
    }
    (out_dir / "qa-smoke-dig-last.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return results
