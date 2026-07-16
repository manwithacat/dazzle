"""Pure agent closed-loop operations (#1605).

No imports from ``dazzle.mcp`` — safe under dual-lock pins that omit the
``mcp`` extra (CyFuture pilot feedback P0).
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from typing import Any

from dazzle.agent_loop.journey_prove import prove_stories_journey
from dazzle.agent_loop.runtime_prove import (
    prove_stories_runtime,
    service_contract_diff_deep,
)
from dazzle.core.appspec_loader import load_project_appspec


def runtime_truth(project_root: Path) -> dict[str, Any]:
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


def host_inventory(project_root: Path) -> dict[str, Any]:
    """routes/ + services/ dual-lock surface."""
    routes_dir = project_root / "routes"
    services_dir = project_root / "services"
    overrides: list[dict[str, Any]] = []
    if routes_dir.is_dir():
        try:
            from dazzle.http.runtime.route_overrides import discover_route_overrides

            for o in discover_route_overrides(routes_dir):
                try:
                    src = str(o.source_path.relative_to(project_root))
                except ValueError:
                    src = str(o.source_path)
                overrides.append(
                    {
                        "method": o.method,
                        "path": o.path,
                        "source": src,
                        "implements_entity": getattr(o, "implements_entity", None),
                        "implements_op": getattr(o, "implements_op", None),
                    }
                )
        except Exception as exc:
            overrides = [{"error": str(exc)[:200]}]

    service_files: list[str] = []
    if services_dir.is_dir():
        service_files = sorted(p.name for p in services_dir.glob("*.py") if p.name != "__init__.py")

    handlers: list[str] = []
    for cand in (
        project_root / "dsl" / "story_handlers.py",
        project_root / "story_handlers.py",
    ):
        if cand.is_file():
            handlers.append(str(cand.relative_to(project_root)))

    route_count = 0
    if overrides and "error" not in overrides[0]:
        route_count = len(overrides)

    return {
        "routes": overrides,
        "route_count": route_count,
        "services_py": service_files,
        "story_handlers": handlers,
        "dual_lock": {
            "has_routes": routes_dir.is_dir() and any(routes_dir.glob("*.py")),
            "has_services": bool(service_files),
            "has_story_handlers": bool(handlers),
        },
    }


def dsl_service_names(appspec: Any) -> list[str]:
    names: list[str] = []
    for svc in getattr(appspec, "domain_services", None) or []:
        n = getattr(svc, "name", None)
        if n:
            names.append(str(n))
    return sorted(names)


def story_binding_summary(appspec: Any) -> dict[str, Any]:
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
    total_acc = len(accepted) or 1
    return {
        "total": len(stories),
        "accepted": len(accepted),
        "accepted_bound": bound,
        "accepted_narrative_only": narrative,
        "accepted_unbound": unbound_accepted,
        "binding_gate": "fail" if unbound_accepted else "pass",
        "narrative_only_ratio": round(narrative / total_acc, 3),
        "executed_by_ratio": round(bound / total_acc, 3),
    }


def _story_row(story: Any, **extra: Any) -> dict[str, Any]:
    return {
        "story_id": story.story_id,
        "title": getattr(story, "title", "") or story.story_id,
        "persona": getattr(story, "persona", "") or "",
        "status": str(getattr(story.status, "value", story.status)),
        "executed_by": str(getattr(story, "executed_by", None) or "") or None,
        "narrative_only": bool(getattr(story, "narrative_only", False)),
        **extra,
    }


def binding_wall(
    project_root: Path,
    appspec: Any | None = None,
) -> dict[str, Any]:
    """Story wall by *execution binding* (#1605 pilot F).

    Buckets agents actually need (not only process-implements coverage):

    - ``executed_pass_static`` — has ``executed_by`` and static prove passes
    - ``executed_fail_static`` — bound but target missing
    - ``narrative_only`` — honesty mode (not implemented path)
    - ``unbound_accepted`` — accepted without bind (validate hard-fail)
    - ``other`` — draft / non-accepted
    """
    if appspec is None:
        appspec = load_project_appspec(project_root)
    stories = list(getattr(appspec, "stories", None) or [])
    buckets: dict[str, list[dict[str, Any]]] = {
        "executed_pass_static": [],
        "executed_fail_static": [],
        "narrative_only": [],
        "unbound_accepted": [],
        "other": [],
    }
    for s in stories:
        status = str(getattr(s.status, "value", s.status))
        if getattr(s, "narrative_only", False):
            buckets["narrative_only"].append(_story_row(s))
            continue
        eb = getattr(s, "executed_by", None)
        if eb:
            proved = _static_prove_one(project_root, appspec, s)
            row = _story_row(
                s,
                prove_result=proved.get("result"),
                prove_reason=proved.get("reason"),
            )
            if str(proved.get("result", "")).startswith("pass"):
                buckets["executed_pass_static"].append(row)
            else:
                buckets["executed_fail_static"].append(row)
            continue
        if status == "accepted":
            buckets["unbound_accepted"].append(_story_row(s))
        else:
            buckets["other"].append(_story_row(s))

    counts = {k: len(v) for k, v in buckets.items()}
    md: list[str] = [
        "Story wall — binding / prove (agent closed loop)",
        "",
        f"Executed + pass_static ({counts['executed_pass_static']})",
    ]
    for r in buckets["executed_pass_static"]:
        md.append(f"  [ok] {r['story_id']}  {r['title']}  → {r.get('executed_by')}")
    md.append("")
    md.append(f"Executed + fail_static ({counts['executed_fail_static']})")
    for r in buckets["executed_fail_static"]:
        md.append(
            f"  [!!] {r['story_id']}  {r['title']}  → {r.get('executed_by')} "
            f"({r.get('prove_reason')})"
        )
    md.append("")
    md.append(f"narrative_only ({counts['narrative_only']})")
    for r in buckets["narrative_only"]:
        md.append(f"  [..] {r['story_id']}  {r['title']}")
    md.append("")
    md.append(f"unbound accepted ({counts['unbound_accepted']})")
    for r in buckets["unbound_accepted"]:
        md.append(f"  [  ] {r['story_id']}  {r['title']}")
    if buckets["other"]:
        md.append("")
        md.append(f"other / draft ({counts['other']})")
        for r in buckets["other"]:
            md.append(f"  [~~] {r['story_id']}  {r['title']}  ({r['status']})")

    return {
        "view": "binding_wall",
        "counts": counts,
        "buckets": buckets,
        "markdown": "\n".join(md),
        "note": (
            "pass_static = binding target exists. "
            "pass_runtime = host module ready. "
            "pass_journey = hub/open-via graph coherent (not Playwright)."
        ),
    }


def _coverage_buckets_light(appspec: Any) -> dict[str, Any]:
    """Process.implements-based buckets without MCP coverage handler."""
    stories = list(getattr(appspec, "stories", None) or [])
    implements: set[str] = set()
    for proc in getattr(appspec, "processes", None) or []:
        for sid in getattr(proc, "implements", None) or []:
            implements.add(str(sid))
    covered = partial = uncovered = 0
    for s in stories:
        sid = s.story_id
        if sid in implements:
            covered += 1
        elif getattr(s, "executed_by", None) or getattr(s, "narrative_only", False):
            partial += 1
        else:
            uncovered += 1
    return {
        "buckets": {
            "covered": covered,
            "partial": partial,
            "uncovered": uncovered,
            "other": 0,
        },
        "story_rows": len(stories),
        "source": "implements_light",
    }


def process_summary(appspec: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for proc in getattr(appspec, "processes", None) or []:
        steps = []
        for step in getattr(proc, "steps", None) or []:
            ht = getattr(step, "human_task", None)
            steps.append(
                {
                    "name": getattr(step, "name", None),
                    "kind": str(getattr(step, "kind", None) or getattr(step, "type", "") or ""),
                    "service": getattr(step, "service", None) or getattr(step, "service_ref", None),
                    "surface": getattr(step, "surface", None)
                    or (getattr(ht, "surface", None) if ht else None),
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


def next_steps(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Exact next CLI/MCP calls — prefer CLI so dual-lock pins without mcp work."""
    steps: list[dict[str, str]] = []
    binding = payload.get("story_bindings") or {}
    unbound = binding.get("accepted_unbound") or []
    host = payload.get("host") or {}
    dual = host.get("dual_lock") or {}
    narr_ratio = binding.get("narrative_only_ratio") or 0

    if unbound:
        sid = unbound[0]
        steps.append(
            {
                "rank": "1",
                "kind": "cli",
                "command": (
                    f"Bind accepted story {sid} (executed_by or narrative_only), then "
                    f"`dazzle prove story {sid} --static` "
                    f"or bulk: `dazzle story bind-migrate --unbound-to narrative_only`"
                ),
            }
        )
    else:
        steps.append(
            {
                "rank": "1",
                "kind": "cli",
                "command": "dazzle prove story --static  # re-check binding evidence (not runtime)",
            }
        )

    if dual.get("has_routes") or dual.get("has_services"):
        steps.append(
            {
                "rank": "2",
                "kind": "cli",
                "command": (
                    "dazzle agent context  # review host dual-lock inventory; "
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

    if narr_ratio >= 0.5:
        steps.append(
            {
                "rank": "3",
                "kind": "cli",
                "command": (
                    f"narrative_only_ratio={narr_ratio} — tech debt; "
                    "promote real executed_by binds for domain STs "
                    "(dazzle story bind-migrate --report)"
                ),
            }
        )
    else:
        steps.append(
            {
                "rank": "3",
                "kind": "cli",
                "command": "dazzle agent playbook domain_logic",
            }
        )
    return steps


def build_context(project_root: Path) -> dict[str, Any]:
    """D1 + D5 — brownfield session-start composition (dict, not JSON)."""
    appspec = load_project_appspec(project_root)
    dsl_services = dsl_service_names(appspec)
    host = host_inventory(project_root)
    host_svc = {Path(n).stem for n in host.get("services_py") or []}
    dsl_set = set(dsl_services)
    domain = getattr(appspec, "domain", None)
    entity_n = len(getattr(domain, "entities", None) or []) if domain is not None else 0
    payload: dict[str, Any] = {
        "ok": True,
        "operation": "context",
        "runtime": runtime_truth(project_root),
        "counts": {
            "entities": entity_n,
            "surfaces": len(getattr(appspec, "surfaces", None) or []),
            "processes": len(getattr(appspec, "processes", None) or []),
            "stories": len(getattr(appspec, "stories", None) or []),
            "services_dsl": len(dsl_services),
            "personas": len(getattr(appspec, "personas", None) or []),
        },
        "story_bindings": story_binding_summary(appspec),
        "story_wall": binding_wall(project_root, appspec),
        "coverage": _coverage_buckets_light(appspec),
        "processes": process_summary(appspec),
        "services": {
            "dsl": dsl_services,
            "host_py": host.get("services_py") or [],
            "matched": sorted(dsl_set & host_svc),
            "dsl_only": sorted(dsl_set - host_svc),
            "host_only": sorted(host_svc - dsl_set),
            # Light contract diff: DSL declared without host file, or host without DSL.
            "contract_diff": {
                "missing_host_impl": sorted(dsl_set - host_svc),
                "orphan_host_py": sorted(host_svc - dsl_set),
                "ok": not (dsl_set - host_svc) and not (host_svc - dsl_set),
            },
        },
        "host": host,
        "thesis": {
            "parent_issue": 1605,
            "loop": "map → bind → scaffold(CLI) → prove --static → coverage gate",
            "adr": "0002-mcp-cli-boundary",
            "evidence_kind": "static",
        },
    }
    try:
        from dazzle.agent_loop.runtime_prove import service_contract_diff_deep

        payload["services"]["contract_diff_deep"] = service_contract_diff_deep(
            project_root, appspec
        )
    except Exception as exc:
        payload["services"]["contract_diff_deep"] = {"error": str(exc)[:200]}
    payload["next_steps"] = next_steps(payload)
    return payload


def _static_prove_one(project_root: Path, appspec: Any, story: Any) -> dict[str, Any]:
    """Static binding evidence only — not a runtime journey pass."""
    sid = story.story_id
    if getattr(story, "narrative_only", False):
        return {
            "story_id": sid,
            "result": "pass_static",
            "evidence_kind": "static",
            "reason": "narrative_only",
            "evidence": [],
            "note": "Honesty mode — not an implemented path",
        }
    eb = getattr(story, "executed_by", None)
    if not eb:
        return {
            "story_id": sid,
            "result": "fail_static",
            "evidence_kind": "static",
            "reason": "unbound",
            "evidence": [],
            "hint": "Set executed_by: … or narrative_only: true",
        }
    eb_s = str(eb).strip()
    evidence: list[str] = []
    ok = False
    reason = "unknown_binding_shape"

    if eb_s.startswith("process."):
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
        dsl_names = set(dsl_service_names(appspec))
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
        "result": "pass_static" if ok else "fail_static",
        "evidence_kind": "static",
        "reason": reason,
        "evidence": evidence,
        "note": "Binding evidence only — not a runtime journey pass",
    }


def prove_stories(
    project_root: Path,
    *,
    story_id: str | None = None,
    mode: str = "static",
) -> dict[str, Any]:
    """Prove stories: static binding, runtime host readiness, or journey graph.

    - ``static`` → ``pass_static`` / ``fail_static`` (target exists in DSL/host map)
    - ``runtime`` → host-module readiness (``pass_runtime`` / …). Not browser e2e.
    - ``journey`` → surface hub / open-via hop coherence + process host ready
      (``pass_journey`` / ``fail_journey`` / ``skip_journey``). Still not Playwright.
    """
    appspec = load_project_appspec(project_root)
    stories = list(getattr(appspec, "stories", None) or [])
    if story_id:
        stories = [s for s in stories if s.story_id == story_id]
        if not stories:
            return {"ok": False, "error": f"Story not found: {story_id}"}
    else:
        stories = [
            s
            for s in stories
            if str(getattr(s.status, "value", s.status)) == "accepted"
            or getattr(s, "executed_by", None)
            or getattr(s, "narrative_only", False)
        ]

    static_results = [_static_prove_one(project_root, appspec, s) for s in stories]
    mode_norm = (mode or "static").strip().lower()
    if mode_norm in ("static", ""):
        failed = [r for r in static_results if str(r.get("result", "")).startswith("fail")]
        return {
            "ok": not failed,
            "operation": "prove",
            "evidence_kind": "static",
            "checked": len(static_results),
            "passed": len(static_results) - len(failed),
            "failed": len(failed),
            "results": static_results,
            "note": "pass_static means binding target exists — not that the user journey works",
        }

    if mode_norm in ("runtime", "host"):
        return _prove_runtime_bundle(project_root, appspec, stories, static_results)

    if mode_norm in ("journey", "journey_graph", "path"):
        return _prove_journey_bundle(project_root, appspec, stories, static_results)

    return {
        "ok": False,
        "error": f"Unknown prove mode: {mode}. Use static|runtime|journey",
    }


def _static_pass_fail(static_results: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "passed": sum(1 for r in static_results if str(r.get("result", "")).startswith("pass")),
        "failed": sum(1 for r in static_results if str(r.get("result", "")).startswith("fail")),
    }


def _prove_runtime_bundle(
    project_root: Path,
    appspec: Any,
    stories: list[Any],
    static_results: list[dict[str, Any]],
) -> dict[str, Any]:
    runtime = prove_stories_runtime(project_root, appspec, stories, static_results=static_results)
    runtime["static_summary"] = _static_pass_fail(static_results)
    runtime["service_contract_diff"] = service_contract_diff_deep(project_root, appspec)
    return runtime


def _prove_journey_bundle(
    project_root: Path,
    appspec: Any,
    stories: list[Any],
    static_results: list[dict[str, Any]],
) -> dict[str, Any]:
    runtime = prove_stories_runtime(project_root, appspec, stories, static_results=static_results)
    journey = prove_stories_journey(
        project_root,
        appspec,
        stories,
        static_results=static_results,
        runtime_results=list(runtime.get("results") or []),
    )
    journey["static_summary"] = _static_pass_fail(static_results)
    journey["runtime_summary"] = {
        "passed": runtime.get("passed"),
        "failed": runtime.get("failed"),
        "skipped": runtime.get("skipped"),
    }
    return journey


PLAYBOOK_DOMAIN_LOGIC = """# Playbook: domain_logic closed loop (#1605)

## Thesis
Structure tools are not enough. Domain behaviour lives in services/routes/process.
Agents must **map → bind → scaffold → prove --static**, not dual-lock chrome.

## ADR-0002
- **MCP** — `agent(operation=context|prove|playbook)` when mcp extra installed
- **CLI (default dual-lock path)** — no mcp required:
  - `dazzle agent context`
  - `dazzle prove story --static`
  - `dazzle agent playbook domain_logic`
  - `dazzle scaffold …`
  - `dazzle story bind-migrate …`

## Loop
1. **Map** — `dazzle agent context`
2. **Bind** — `executed_by:` or `narrative_only: true` on every accepted story
3. **Scaffold** — `dazzle scaffold service|story|process-step …`
4. **Prove** — `dazzle prove story --static` (binding evidence only)
5. **Gate** — validate fails accepted+unbound

## Language
- `pass_static` / `fail_static` — binding target exists in DSL/host map
- `pass_runtime` / `fail_runtime` / `skip_runtime` — host module readiness
  (service file, entrypoint, not scaffold-only). **Not** browser e2e.
- `pass_journey` / `fail_journey` / `skip_journey` — surface hub / open-via
  hop graph + process host ready. **Still not** Playwright e2e.
- `dazzle prove story --runtime` / `--journey`

## Story wall (binding)
- `dazzle agent wall` — buckets: executed+pass_static / executed+fail_static /
  narrative_only / unbound_accepted
- MCP `story(operation=get, view=wall)` includes the same binding buckets
- `agent context` → `story_wall` for session start
"""


def build_playbook(name: str = "domain_logic") -> dict[str, Any]:
    n = (name or "domain_logic").strip()
    if n in ("domain_logic", "domain-logic", "default"):
        return {
            "ok": True,
            "operation": "playbook",
            "name": "domain_logic",
            "body": PLAYBOOK_DOMAIN_LOGIC,
        }
    return {"ok": False, "error": f"Unknown playbook: {n}. Known: domain_logic"}


def context_json(project_root: Path) -> str:
    return json.dumps(build_context(project_root), indent=2, default=str)


def prove_json(project_root: Path, *, story_id: str | None = None) -> str:
    return json.dumps(prove_stories(project_root, story_id=story_id), indent=2, default=str)


def playbook_json(name: str = "domain_logic") -> str:
    return json.dumps(build_playbook(name), indent=2)
