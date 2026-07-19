"""Persona-home residual — seeds must populate *my* desks (#1626 re-eval).

Static analysis: for each product persona with a default workspace, find
regions filtered by ``current_user`` / ``current_context`` and count seed
jsonl rows that would satisfy those filters when the login principal is
the stable demo user id for that persona.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Keep in sync with dazzle.http.runtime.test_routes.STABLE_PERSONA_USER_IDS
STABLE_PERSONA_USER_IDS: dict[str, str] = {
    "member": "a1000000-0000-4000-8000-000000000001",
    "manager": "a1000000-0000-4000-8000-000000000002",
    "admin": "a1000000-0000-4000-8000-000000000003",
    "agent": "a1000000-0000-4000-8000-000000000004",
    "customer": "a1000000-0000-4000-8000-000000000005",
    "requester": "a1000000-0000-4000-8000-000000000006",
    "approver": "a1000000-0000-4000-8000-000000000007",
    "finance": "a1000000-0000-4000-8000-000000000008",
    "auditor": "a1000000-0000-4000-8000-000000000009",
    "user": "a1000000-0000-4000-8000-00000000000a",
    "designer": "a1000000-0000-4000-8000-00000000000b",
    "reviewer": "a1000000-0000-4000-8000-00000000000c",
    "tester": "a1000000-0000-4000-8000-00000000000d",
    "engineer": "a1000000-0000-4000-8000-00000000000e",
    "ops_engineer": "a1000000-0000-4000-8000-00000000000f",
    "employee": "a1000000-0000-4000-8000-000000000010",
    "hr_admin": "a1000000-0000-4000-8000-000000000011",
    "tenant_admin": "a1000000-0000-4000-8000-000000000012",
    "finance_admin": "a1000000-0000-4000-8000-000000000013",
}

# Framework-injected platform desk — not a product home for antagonist scoring.
_PLATFORM_WORKSPACES = frozenset({"_platform_admin", "platform_admin"})

_PLATFORM_PERSONAS = frozenset({"admin", "platform_admin", "superuser", "operator", "sysadmin"})

_PERSONA_HEADER_RE = re.compile(r'^persona\s+(\w+)\s+"([^"]*)"')
_WORKSPACE_HEADER_RE = re.compile(r'^workspace\s+(\w+)\s+"([^"]*)"\s*:')
_DEFAULT_WS_RE = re.compile(r"default_workspace:\s*(\w+)")
_SOURCE_RE = re.compile(r"source:\s*(\w+)")
_FILTER_RE = re.compile(r"filter:\s*(.+)")
_CURRENT_USER_RE = re.compile(
    r"(assigned_to|assigned_to_id|created_by|submitted_by|reported_by_id|"
    r"owner|assigned_tester_id|tester_id|requester)\s*=\s*current_user"
)
_CURRENT_CONTEXT_RE = re.compile(r"(assigned_to|created_by|submitted_by)\s*=\s*current_context")
_STATUS_RE = re.compile(r"status\s*=\s*(\w+)")
_REGION_HEADER_RE = re.compile(r"^  (\w+):\s*$")

_SKIP_REGION_NAMES = frozenset(
    {
        "access",
        "purpose",
        "stage",
        "as",
        "layout",
        "context_selector",
    }
)


@dataclass
class PersonaHomeRegion:
    region: str
    source: str
    filter_text: str
    bind_field: str
    status: str | None
    seed_hits: int
    residual: bool
    reason: str = ""


@dataclass
class PersonaHome:
    persona: str
    default_workspace: str | None
    stable_user_id: str | None
    regions: list[PersonaHomeRegion] = field(default_factory=list)

    @property
    def residual(self) -> bool:
        return any(r.residual for r in self.regions)

    @property
    def residual_reasons(self) -> list[str]:
        return [f"{r.region}:{r.reason}" for r in self.regions if r.residual]


def _read_dsl(app_dir: Path) -> str:
    dsl = app_dir / "dsl"
    if not dsl.is_dir():
        return ""
    parts: list[str] = []
    for p in sorted(dsl.rglob("*.dsl")):
        try:
            parts.append(p.read_text(encoding="utf-8"))
        except OSError:
            continue
    return "\n".join(parts)


def _seed_dir(app_dir: Path) -> Path | None:
    for cand in (
        app_dir / "dsl" / "seeds" / "demo_data",
        app_dir / ".dazzle" / "demo_data",
        app_dir / "demo_data",
    ):
        if cand.is_dir():
            return cand
    return None


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _count_seed_hits(
    rows: list[dict[str, Any]],
    *,
    bind_field: str,
    user_id: str,
    status: str | None,
) -> int:
    n = 0
    for r in rows:
        if str(r.get(bind_field) or "") != user_id:
            continue
        if status is not None and str(r.get("status") or "") != status:
            continue
        n += 1
    return n


def _indented_block_bodies(text: str) -> list[tuple[str, str, str]]:
    """Parse top-level ``kind name "label":`` blocks with indented bodies.

    Returns list of (kind, name, body) where body includes blank lines and
    nested indented content until the next non-indented non-blank line.
    """
    lines = text.splitlines(keepends=True)
    out: list[tuple[str, str, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith("persona "):
            m = _PERSONA_HEADER_RE.match(stripped)
            if m and ":" in line:
                name = m.group(1)
                i += 1
                body_lines: list[str] = []
                while i < n:
                    ln = lines[i]
                    if ln.strip() == "":
                        body_lines.append(ln)
                        i += 1
                        continue
                    if ln[0] not in " \t":
                        break
                    body_lines.append(ln)
                    i += 1
                out.append(("persona", name, "".join(body_lines)))
                continue
        if stripped.startswith("workspace "):
            m = _WORKSPACE_HEADER_RE.match(stripped.rstrip("\n"))
            if m:
                name = m.group(1)
                i += 1
                body_lines = []
                while i < n:
                    ln = lines[i]
                    if ln.strip() == "":
                        body_lines.append(ln)
                        i += 1
                        continue
                    if ln[0] not in " \t":
                        break
                    body_lines.append(ln)
                    i += 1
                out.append(("workspace", name, "".join(body_lines)))
                continue
        i += 1
    return out


def _parse_workspace_regions(body: str) -> list[dict[str, str]]:
    """Extract regions with source + filter from a workspace body."""
    out: list[dict[str, str]] = []
    lines = body.splitlines(keepends=True)
    i = 0
    n = len(lines)
    while i < n:
        m = _REGION_HEADER_RE.match(lines[i].rstrip("\n"))
        if not m:
            i += 1
            continue
        region = m.group(1)
        i += 1
        block_lines: list[str] = []
        while i < n:
            ln = lines[i]
            if ln.strip() == "":
                # peek: blank inside block only if next non-blank is deeper
                j = i + 1
                while j < n and lines[j].strip() == "":
                    j += 1
                if j < n and lines[j].startswith("    "):
                    block_lines.append(ln)
                    i += 1
                    continue
                break
            if ln.startswith("    "):
                block_lines.append(ln)
                i += 1
                continue
            # next 2-space region header or other peer
            break
        if region in _SKIP_REGION_NAMES:
            continue
        block = "".join(block_lines)
        sm = _SOURCE_RE.search(block)
        if not sm:
            continue
        fm = _FILTER_RE.search(block)
        filter_text = fm.group(1).strip() if fm else ""
        out.append(
            {
                "region": region,
                "source": sm.group(1),
                "filter": filter_text,
            }
        )
    return out


def _collect_personas_and_workspaces(
    text: str,
) -> tuple[list[tuple[str, str | None]], dict[str, str]]:
    personas: list[tuple[str, str | None]] = []
    workspaces: dict[str, str] = {}
    for kind, name, body in _indented_block_bodies(text):
        if kind == "persona":
            if name.lower() in _PLATFORM_PERSONAS and name.lower() != "admin":
                continue
            dws = _DEFAULT_WS_RE.search(body)
            personas.append((name, dws.group(1) if dws else None))
        elif kind == "workspace":
            workspaces[name] = body
    return personas, workspaces


def _score_region(
    reg: dict[str, str],
    *,
    uid: str | None,
    seed: Path | None,
    min_hits: int,
) -> PersonaHomeRegion | None:
    """Score one current_user region; None if org-scoped (no persona bind)."""
    filter_text = reg["filter"]
    bind_m = _CURRENT_USER_RE.search(filter_text) or _CURRENT_CONTEXT_RE.search(filter_text)
    if not bind_m:
        return None
    bind_field = bind_m.group(1)
    status_m = _STATUS_RE.search(filter_text)
    status = status_m.group(1) if status_m else None
    source = reg["source"]

    if not uid:
        return PersonaHomeRegion(
            region=reg["region"],
            source=source,
            filter_text=filter_text,
            bind_field=bind_field,
            status=status,
            seed_hits=0,
            residual=True,
            reason="no_stable_user_id",
        )

    rows = _load_jsonl(seed / f"{source}.jsonl") if seed is not None else []
    if not rows:
        return PersonaHomeRegion(
            region=reg["region"],
            source=source,
            filter_text=filter_text,
            bind_field=bind_field,
            status=status,
            seed_hits=0,
            residual=True,
            reason=f"missing_seed_jsonl:{source}",
        )

    hits = _count_seed_hits(rows, bind_field=bind_field, user_id=uid, status=status)
    residual = hits < min_hits
    return PersonaHomeRegion(
        region=reg["region"],
        source=source,
        filter_text=filter_text,
        bind_field=bind_field,
        status=status,
        seed_hits=hits,
        residual=residual,
        reason=f"seed_hits={hits}<{min_hits}" if residual else f"seed_hits={hits}",
    )


def _score_one_persona(
    pid: str,
    dws: str | None,
    workspaces: dict[str, str],
    *,
    seed: Path | None,
    min_hits: int,
) -> PersonaHome:
    home = PersonaHome(
        persona=pid,
        default_workspace=dws,
        stable_user_id=STABLE_PERSONA_USER_IDS.get(pid),
    )
    # Product admin must not land on framework platform chrome (#1626 P0-3/4).
    if dws and dws in _PLATFORM_WORKSPACES:
        home.regions.append(
            PersonaHomeRegion(
                region="-",
                source="-",
                filter_text="",
                bind_field="",
                status=None,
                seed_hits=0,
                residual=True,
                reason=f"platform_admin_landing:{dws}",
            )
        )
        return home
    if not dws or dws not in workspaces:
        if dws:
            home.regions.append(
                PersonaHomeRegion(
                    region="-",
                    source="-",
                    filter_text="",
                    bind_field="",
                    status=None,
                    seed_hits=0,
                    residual=True,
                    reason=f"workspace_missing:{dws}",
                )
            )
        return home

    for reg in _parse_workspace_regions(workspaces[dws]):
        scored = _score_region(reg, uid=home.stable_user_id, seed=seed, min_hits=min_hits)
        if scored is not None:
            home.regions.append(scored)
    return home


def score_persona_homes(app_dir: Path, *, min_hits: int = 1) -> list[PersonaHome]:
    """Score assignment-aware persona homes for one app directory."""
    text = _read_dsl(app_dir)
    if not text.strip():
        return []

    personas, workspaces = _collect_personas_and_workspaces(text)
    seed = _seed_dir(app_dir)
    return [
        _score_one_persona(pid, dws, workspaces, seed=seed, min_hits=min_hits)
        for pid, dws in personas
    ]
