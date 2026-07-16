"""#1605 agent-first closed loop — MCP read surface.

Operations (ADR-0002: all read-only / report-only):
- ``context`` — D1 brownfield map + D5 runtime.truth + next steps
- ``prove`` — D4 static evidence for bound stories
- ``playbook`` — D6 domain_logic playbook markdown

CLI owns scaffold/write (``dazzle scaffold`` / ``dazzle prove``).
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from typing import Any

from dazzle.mcp.server.handlers.common import (
    error_response,
    extract_progress,
    load_project_appspec,
    wrap_handler_errors,
)

# Binding kinds accepted by #1608 / StorySpec.executed_by
_BINDING_PREFIXES = (
    "process.",
    "service.",
    "surface.",
    "host_route ",
)


def _runtime_truth(project_root: Path) -> dict[str, Any]:
    """D5 — which pin/Python the agent is talking to."""
    out: dict[str, Any] = {
        "python": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "cwd": str(Path.cwd()),
        "project_root": str(project_root.resolve()),
    }
    try:
        from dazzle._version import get_version

        out["dazzle_version"] = get_version()
    except Exception:
        out["dazzle_version"] = "unknown"
    try:
        import subprocess

        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_root,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).strip()
        out["git_head"] = sha
    except Exception:
        out["git_head"] = None
    manifest = project_root / "dazzle.toml"
    out["has_dazzle_toml"] = manifest.is_file()
    if manifest.is_file():
        try:
            from dazzle.core.manifest import load_manifest

            m = load_manifest(manifest)
            out["manifest_name"] = m.name
            out["manifest_version"] = getattr(m, "version", None)
        except Exception as exc:
            out["manifest_error"] = str(exc)[:200]
    return out


def _host_inventory(project_root: Path) -> dict[str, Any]:
    """routes/ + services/ dual-lock surface."""
    routes_dir = project_root / "routes"
    services_dir = project_root / "services"
    overrides: list[dict[str, Any]] = []
    if routes_dir.is_dir():
        try:
            from dazzle.http.runtime.route_overrides import discover_route_overrides

            for o in discover_route_overrides(routes_dir):
                overrides.append(
                    {
                        "method": o.method,
                        "path": o.path,
                        "source": str(o.source_path.relative_to(project_root))
                        if o.source_path.is_relative_to(project_root)
                        else str(o.source_path),
                        "implements_entity": getattr(o, "implements_entity", None),
                        "implements_op": getattr(o, "implements_op", None),
                    }
                )
        except Exception as exc:
            overrides = [{"error": str(exc)[:200]}]

    service_files: list[str] = []
    if services_dir.is_dir():
        service_files = sorted(p.name for p in services_dir.glob("*.py") if p.name != "__init__.py")

    handlers = []
    for cand in (
        project_root / "dsl" / "story_handlers.py",
        project_root / "story_handlers.py",
    ):
        if cand.is_file():
            handlers.append(str(cand.relative_to(project_root)))

    return {
        "routes": overrides,
        "route_count": len(overrides) if overrides and "error" not in overrides[0] else 0,
        "services_py": service_files,
        "story_handlers": handlers,
        "dual_lock": {
            "has_routes": routes_dir.is_dir() and any(routes_dir.glob("*.py")),
            "has_services": bool(service_files),
            "has_story_handlers": bool(handlers),
        },
    }


def _dsl_service_names(appspec: Any) -> list[str]:
    names: list[str] = []
    for svc in getattr(appspec, "services", None) or []:
        n = getattr(svc, "name", None)
        if n:
            names.append(str(n))
    # domain_services alias on some appspecs
    for svc in getattr(appspec, "domain_services", None) or []:
        n = getattr(svc, "name", None)
        if n and n not in names:
            names.append(str(n))
    return sorted(names)


def _story_binding_summary(appspec: Any) -> dict[str, Any]:
    stories = list(getattr(appspec, "stories", None) or [])
    accepted = [s for s in stories if str(getattr(s.status, "value", s.status)) == "accepted"]
    bound = 0
    narrative = 0
    unbound_accepted: list[str] = []
    for s in accepted:
        if getattr(s, "narrative_only", False):
            narrative += 1
            continue
        eb = getattr(s, "executed_by", None)
        if eb:
            bound += 1
        else:
            unbound_accepted.append(s.story_id)
    return {
        "total": len(stories),
        "accepted": len(accepted),
        "accepted_bound": bound,
        "accepted_narrative_only": narrative,
        "accepted_unbound": unbound_accepted,
        "binding_gate": "fail" if unbound_accepted else "pass",
    }


def _coverage_buckets(project_root: Path) -> dict[str, Any]:
    """Reuse process coverage statuses without reimplementing the wall."""
    try:
        from dazzle.mcp.server.handlers.process import stories_coverage_handler

        raw = stories_coverage_handler(project_root, {"limit": 500})
        data = json.loads(raw)
    except Exception as exc:
        return {"error": str(exc)[:200], "buckets": {}}
    buckets: dict[str, int] = {"covered": 0, "partial": 0, "uncovered": 0, "other": 0}
    for item in data.get("stories") or []:
        st = item.get("status") or "uncovered"
        if st in buckets:
            buckets[st] += 1
        else:
            buckets["other"] += 1
    return {"buckets": buckets, "story_rows": len(data.get("stories") or [])}


def _process_summary(appspec: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for proc in getattr(appspec, "processes", None) or []:
        steps = []
        for step in getattr(proc, "steps", None) or []:
            steps.append(
                {
                    "name": getattr(step, "name", None),
                    "kind": str(getattr(step, "kind", None) or getattr(step, "type", "") or ""),
                    "service": getattr(step, "service", None) or getattr(step, "service_ref", None),
                    "surface": getattr(step, "surface", None)
                    or getattr(step, "human_task", None)
                    and getattr(getattr(step, "human_task", None), "surface", None),
                }
            )
        out.append(
            {
                "name": proc.name,
                "implements": list(getattr(proc, "implements", None) or []),
                "step_count": len(steps),
                "steps": steps[:40],
            }
        )
    return out


def _next_steps(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Exact next tool/CLI calls — the closed-loop prompt for agents."""
    steps: list[dict[str, str]] = []
    binding = payload.get("story_bindings") or {}
    unbound = binding.get("accepted_unbound") or []
    host = payload.get("host") or {}
    dual = host.get("dual_lock") or {}

    if unbound:
        sid = unbound[0]
        steps.append(
            {
                "rank": "1",
                "kind": "dsl",
                "command": (
                    f"Bind accepted story {sid}: set `executed_by: …` or "
                    f"`narrative_only: true` in stories.dsl, then "
                    f"`dazzle prove story {sid}`"
                ),
            }
        )
    else:
        steps.append(
            {
                "rank": "1",
                "kind": "mcp",
                "command": "agent(operation='prove') — re-check binding evidence",
            }
        )

    if dual.get("has_routes") or dual.get("has_services"):
        steps.append(
            {
                "rank": "2",
                "kind": "mcp",
                "command": (
                    "Review host dual-lock inventory in agent.context.host; "
                    "prefer DSL bind over growing routes/"
                ),
            }
        )
    else:
        steps.append(
            {
                "rank": "2",
                "kind": "cli",
                "command": "dazzle scaffold service <name>  # after declaring service in DSL",
            }
        )

    steps.append(
        {
            "rank": "3",
            "kind": "mcp",
            "command": "agent(operation='playbook', name='domain_logic')",
        }
    )
    return steps


@wrap_handler_errors
def agent_context_handler(project_root: Path, args: dict[str, Any]) -> str:
    """D1 + D5 — brownfield session-start composition."""
    progress = extract_progress(args)
    progress.log_sync("Building agent_context…")
    appspec = load_project_appspec(project_root)

    dsl_services = _dsl_service_names(appspec)
    host = _host_inventory(project_root)
    host_svc = {Path(n).stem for n in host.get("services_py") or []}
    dsl_set = set(dsl_services)

    domain = getattr(appspec, "domain", None)
    entity_n = len(getattr(domain, "entities", None) or []) if domain is not None else 0
    counts = {
        "entities": entity_n,
        "surfaces": len(getattr(appspec, "surfaces", None) or []),
        "processes": len(getattr(appspec, "processes", None) or []),
        "stories": len(getattr(appspec, "stories", None) or []),
        "services_dsl": len(dsl_services),
        "personas": len(getattr(appspec, "personas", None) or []),
    }

    payload: dict[str, Any] = {
        "ok": True,
        "operation": "context",
        "runtime": _runtime_truth(project_root),
        "counts": counts,
        "story_bindings": _story_binding_summary(appspec),
        "coverage": _coverage_buckets(project_root),
        "processes": _process_summary(appspec),
        "services": {
            "dsl": dsl_services,
            "host_py": host.get("services_py") or [],
            "matched": sorted(dsl_set & host_svc),
            "dsl_only": sorted(dsl_set - host_svc),
            "host_only": sorted(host_svc - dsl_set),
        },
        "host": host,
        "thesis": {
            "parent_issue": 1605,
            "loop": "map → bind → scaffold(CLI) → prove → coverage gate",
            "adr": "0002-mcp-cli-boundary",
        },
    }
    payload["next_steps"] = _next_steps(payload)
    return json.dumps(payload, indent=2, default=str)


def _static_prove_one(project_root: Path, appspec: Any, story: Any) -> dict[str, Any]:
    """D4 v1 — binding target exists in appspec / filesystem."""
    sid = story.story_id
    if getattr(story, "narrative_only", False):
        return {
            "story_id": sid,
            "result": "pass",
            "reason": "narrative_only",
            "evidence": [],
        }
    eb = getattr(story, "executed_by", None)
    if not eb:
        return {
            "story_id": sid,
            "result": "fail",
            "reason": "unbound",
            "evidence": [],
            "hint": "Set executed_by: … or narrative_only: true",
        }
    eb_s = str(eb).strip()
    evidence: list[str] = []
    ok = False
    reason = "unknown_binding_shape"

    if eb_s.startswith("process."):
        # process.<name> or process.<name>.step.<step>
        parts = eb_s.split(".")
        pname = parts[1] if len(parts) > 1 else ""
        step_name = parts[3] if len(parts) >= 4 and parts[2] == "step" else None
        for proc in getattr(appspec, "processes", None) or []:
            if proc.name != pname:
                continue
            if step_name is None:
                ok = True
                evidence.append(f"process:{pname}")
                reason = "process_exists"
                break
            for step in getattr(proc, "steps", None) or []:
                if getattr(step, "name", None) == step_name:
                    ok = True
                    evidence.append(f"process:{pname}.step:{step_name}")
                    reason = "process_step_exists"
                    break
        if not ok:
            reason = f"process_not_found:{pname}"

    elif eb_s.startswith("service."):
        sname = eb_s.split(".", 1)[1]
        dsl_names = set(_dsl_service_names(appspec))
        host_files = (
            {p.stem for p in (project_root / "services").glob("*.py") if p.name != "__init__.py"}
            if (project_root / "services").is_dir()
            else set()
        )
        if sname in dsl_names:
            evidence.append(f"dsl_service:{sname}")
            ok = True
            reason = "service_in_dsl"
        if sname in host_files:
            evidence.append(f"services/{sname}.py")
            ok = True
            reason = "service_in_host" if reason != "service_in_dsl" else "service_dsl_and_host"
        if not ok:
            reason = f"service_missing:{sname}"

    elif eb_s.startswith("surface."):
        # surface.<name> or surface.<name>.action.<action>
        parts = eb_s.split(".")
        sname = parts[1] if len(parts) > 1 else ""
        for surf in getattr(appspec, "surfaces", None) or []:
            if surf.name == sname:
                ok = True
                evidence.append(f"surface:{sname}")
                reason = "surface_exists"
                if len(parts) >= 4 and parts[2] == "action":
                    aname = parts[3]
                    actions = getattr(surf, "actions", None) or []
                    if any(getattr(a, "name", None) == aname for a in actions):
                        evidence.append(f"surface:{sname}.action:{aname}")
                        reason = "surface_action_exists"
                    else:
                        ok = False
                        reason = f"action_missing:{aname}"
                break
        if not ok and reason == "unknown_binding_shape":
            reason = f"surface_not_found:{sname}"

    elif eb_s.lower().startswith("host_route "):
        rest = eb_s.split(None, 1)[1] if " " in eb_s else ""
        bits = rest.split(None, 1)
        method = bits[0].upper() if bits else "GET"
        path = bits[1] if len(bits) > 1 else ""
        try:
            from dazzle.http.runtime.route_overrides import discover_route_overrides

            for o in discover_route_overrides(project_root / "routes"):
                if o.method == method and o.path == path:
                    ok = True
                    evidence.append(f"{method} {path} <- {o.source_path.name}")
                    reason = "host_route_registered"
                    break
        except Exception as exc:
            reason = f"host_route_scan_error:{exc}"
        if not ok and reason == "unknown_binding_shape":
            reason = f"host_route_missing:{method} {path}"
    else:
        reason = f"invalid_executed_by:{eb_s}"

    return {
        "story_id": sid,
        "executed_by": eb_s,
        "result": "pass" if ok else "fail",
        "reason": reason,
        "evidence": evidence,
    }


@wrap_handler_errors
def agent_prove_handler(project_root: Path, args: dict[str, Any]) -> str:
    """D4 — static prove for one story or all accepted."""
    appspec = load_project_appspec(project_root)
    story_id = args.get("story_id") or args.get("name")
    stories = list(getattr(appspec, "stories", None) or [])
    if story_id:
        stories = [s for s in stories if s.story_id == story_id]
        if not stories:
            return error_response(f"Story not found: {story_id}")
    else:
        stories = [
            s
            for s in stories
            if str(getattr(s.status, "value", s.status)) == "accepted"
            or getattr(s, "executed_by", None)
            or getattr(s, "narrative_only", False)
        ]

    results = [_static_prove_one(project_root, appspec, s) for s in stories]
    failed = [r for r in results if r.get("result") == "fail"]
    return json.dumps(
        {
            "ok": not failed,
            "operation": "prove",
            "checked": len(results),
            "passed": len(results) - len(failed),
            "failed": len(failed),
            "results": results,
        },
        indent=2,
    )


_PLAYBOOK_DOMAIN_LOGIC = """# Playbook: domain_logic closed loop (#1605)

## Thesis
MCP inspects structure. Domain behaviour lives in services/routes/process.
Agents must **map → bind → scaffold → prove**, not dual-lock chrome.

## ADR-0002
- **MCP** — `agent(operation=context|prove|playbook)` (read/report only)
- **CLI** — `dazzle scaffold …`, `dazzle prove story …` (writes / runs)

## Loop
1. **Map** — `agent(operation="context")`
   Brownfield inventory: counts, coverage buckets, routes/, services/, bindings, next_steps.
2. **Bind** — every `status: accepted` story needs either
   - `executed_by: process.<p>.step.<s>`
   - `executed_by: service.<name>`
   - `executed_by: surface.<name>` / `surface.<name>.action.<a>`
   - `executed_by: host_route METHOD /path`
   - or `narrative_only: true`
3. **Scaffold** — `dazzle scaffold service <name>` / `dazzle scaffold process-step …` / `dazzle scaffold story <ST-id>`
4. **Prove** — `agent(operation="prove")` or `dazzle prove story <ST-id>`
   v1 is static evidence (target exists). v2 e2e later.
5. **Gate** — validate fails accepted+unbound stories.

## Anti-patterns
- Green lint + empty dual-lock growth
- Story wall "not started" fixed by stubs that are never on the hot path
- Host routes without `executed_by: host_route …` honesty
"""


@wrap_handler_errors
def agent_playbook_handler(project_root: Path, args: dict[str, Any]) -> str:
    """D6 — playbook resources."""
    name = (args.get("name") or "domain_logic").strip()
    if name in ("domain_logic", "domain-logic", "default"):
        return json.dumps(
            {
                "ok": True,
                "operation": "playbook",
                "name": "domain_logic",
                "body": _PLAYBOOK_DOMAIN_LOGIC,
            },
            indent=2,
        )
    return error_response(f"Unknown playbook: {name}. Known: domain_logic")


def handle_agent(arguments: dict[str, Any]) -> str:
    """Dispatch agent tool operations (wired from handlers_consolidated)."""
    # Prefer the shared project dispatcher when available.
    try:
        from dazzle.mcp.server.handlers_consolidated import _dispatch_project_ops

        return _dispatch_project_ops(
            arguments,
            {
                "context": agent_context_handler,
                "prove": agent_prove_handler,
                "playbook": agent_playbook_handler,
            },
            "agent",
        )
    except Exception:
        # Fallback for unit tests that call handlers with explicit root.
        op = arguments.get("operation") or "context"
        root = arguments.get("project_root") or arguments.get("_resolved_project_path")
        if root is None:
            return error_response("project path required")
        project_path = Path(root)
        if op == "context":
            return agent_context_handler(project_path, arguments)
        if op == "prove":
            return agent_prove_handler(project_path, arguments)
        if op == "playbook":
            return agent_playbook_handler(project_path, arguments)
        return error_response(f"Unknown agent operation: {op}")
