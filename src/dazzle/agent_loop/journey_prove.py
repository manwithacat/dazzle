"""#1605 journey-layer prove — story-tied surface/process graph (no browser).

Does **not** drive Playwright or hit a live server. After static binding
passes, checks that the **declared journey shape** is coherent:

- VIEW hub has sections and/or related groups (not an empty shell)
- LIST ``open:`` hops land on entities that have a VIEW surface
- LIST same-entity detail exists when no open-via
- process bindings: host-ready steps (via runtime prove) + any surface
  step targets exist as journey-ready surfaces

Results: ``pass_journey`` / ``fail_journey`` / ``skip_journey``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dazzle.agent_loop.runtime_prove import runtime_prove_one


def _surfaces_by_entity(appspec: Any) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for surf in getattr(appspec, "surfaces", None) or []:
        ent = getattr(surf, "entity_ref", None) or ""
        if ent:
            out.setdefault(str(ent), []).append(surf)
    return out


def _mode_val(surf: Any) -> str:
    m = getattr(surf, "mode", None)
    return str(getattr(m, "value", m) or "").lower()


def _find_surface(appspec: Any, name: str) -> Any | None:
    for surf in getattr(appspec, "surfaces", None) or []:
        if getattr(surf, "name", None) == name:
            return surf
    return None


def _view_surfaces_for(entity: str, by_ent: dict[str, list[Any]]) -> list[Any]:
    return [s for s in by_ent.get(entity, []) if _mode_val(s) == "view"]


def _check_view_hub(surf: Any) -> tuple[list[str], list[str]]:
    evidence: list[str] = []
    reasons: list[str] = []
    sections = list(getattr(surf, "sections", None) or [])
    related = list(getattr(surf, "related_groups", None) or [])
    if sections:
        evidence.append(f"view_sections:{len(sections)}")
    if related:
        evidence.append(f"view_related_groups:{len(related)}")
    if not sections and not related:
        reasons.append("view_hub_empty:no_sections_or_related")
    elif len(sections) >= 2:
        evidence.append("view_multi_section_hub")
    if any(getattr(s, "layout", None) == "strip" for s in sections):
        evidence.append("view_has_layout_strip")
    return evidence, reasons


def _resolve_open_target(
    appspec: Any, entity: str, open_entity: str | None, via: str
) -> str | None:
    if open_entity:
        return str(open_entity)
    if not entity or not via or not hasattr(appspec, "get_entity"):
        return None
    ent_spec = appspec.get_entity(entity)
    if ent_spec is None:
        return None
    fld = ent_spec.get_field(via)
    if fld is None or getattr(fld, "type", None) is None:
        return None
    ref = getattr(fld.type, "ref_entity", None)
    return str(ref) if ref else None


def _open_hops(surf: Any) -> list[tuple[str | None, str]]:
    open_targets = list(getattr(surf, "open_via_targets", None) or [])
    if open_targets:
        return [
            (getattr(t, "entity", None), str(getattr(t, "via", "") or "")) for t in open_targets
        ]
    open_via = getattr(surf, "open_via", None)
    if open_via:
        return [(getattr(surf, "open_entity", None), str(open_via))]
    return []


def _check_list_hops(
    appspec: Any, surf: Any, entity: str, by_ent: dict[str, list[Any]]
) -> tuple[list[str], list[str]]:
    evidence: list[str] = []
    reasons: list[str] = []
    hops = _open_hops(surf)
    if not hops:
        if entity:
            views = _view_surfaces_for(str(entity), by_ent)
            if not views:
                reasons.append(f"list_no_view_surface:{entity}")
            else:
                evidence.append(f"list_detail_view:{views[0].name}")
        return evidence, reasons
    for open_entity, via in hops:
        target = _resolve_open_target(appspec, entity, open_entity, via)
        if not target:
            reasons.append(f"open_via_unresolved:{via or '?'}")
            continue
        views = _view_surfaces_for(str(target), by_ent)
        if not views:
            reasons.append(f"open_via_no_view_surface:{target}")
        else:
            evidence.append(f"open_hop:{via}->{target}:view:{views[0].name}")
    return evidence, reasons


def _surface_journey_checks(appspec: Any, surf: Any) -> tuple[bool, list[str], list[str]]:
    """Return (ok, evidence, reasons)."""
    name = getattr(surf, "name", "?")
    mode = _mode_val(surf)
    evidence = [f"surface:{name}:mode:{mode or '?'}"]
    reasons: list[str] = []
    by_ent = _surfaces_by_entity(appspec)
    entity = getattr(surf, "entity_ref", None) or ""

    if mode in ("list", "view", "create", "edit") and not entity:
        return False, evidence, ["surface_missing_entity_ref"]

    if mode == "view":
        ev, rs = _check_view_hub(surf)
        evidence.extend(ev)
        reasons.extend(rs)
    elif mode == "list":
        ev, rs = _check_list_hops(appspec, surf, entity, by_ent)
        evidence.extend(ev)
        reasons.extend(rs)

    ok = not reasons
    if ok:
        reasons.append("journey_surface_ok")
    return ok, evidence, reasons


def _prove_surface_binding(appspec: Any, eb: str, evidence: list[str], reasons: list[str]) -> bool:
    sname = eb.split(".")[1] if "." in eb else ""
    surf = _find_surface(appspec, sname)
    if surf is None:
        reasons.append(f"surface_missing:{sname}")
        return False
    s_ok, s_ev, s_reasons = _surface_journey_checks(appspec, surf)
    evidence.extend(s_ev)
    if not s_ok:
        reasons.extend(s_reasons)
        return False
    reasons.append("journey_surface_ok")
    return True


def _prove_process_surfaces(
    appspec: Any, pname: str, evidence: list[str], reasons: list[str]
) -> bool:
    ok = True
    for proc in getattr(appspec, "processes", None) or []:
        if proc.name != pname:
            continue
        for step in getattr(proc, "steps", None) or []:
            target = getattr(step, "surface", None) or getattr(step, "surface_ref", None)
            if not target:
                continue
            surf = _find_surface(appspec, str(target))
            if surf is None:
                ok = False
                reasons.append(f"process_step_surface_missing:{target}")
                continue
            s_ok, s_ev, s_reasons = _surface_journey_checks(appspec, surf)
            evidence.extend(s_ev)
            if not s_ok:
                ok = False
                step_name = getattr(step, "name", "?")
                reasons.extend([f"step:{step_name}:{r}" for r in s_reasons])
        break
    return ok


def _ensure_runtime(
    project_root: Path,
    appspec: Any,
    story: Any,
    static_result: dict[str, Any],
    runtime_result: dict[str, Any] | None,
    evidence: list[str],
    reasons: list[str],
) -> bool:
    rt_res = runtime_result or runtime_prove_one(
        project_root, appspec, story, static_result=static_result
    )
    evidence.extend(rt_res.get("evidence") or [])
    if str(rt_res.get("result", "")).startswith("pass"):
        evidence.append("runtime_pass")
        return True
    reasons.append(f"runtime_not_ready:{rt_res.get('reason')}")
    return False


def _dispatch_binding(
    project_root: Path,
    appspec: Any,
    story: Any,
    eb: str,
    static_result: dict[str, Any],
    runtime_result: dict[str, Any] | None,
    evidence: list[str],
    reasons: list[str],
) -> bool:
    if eb.startswith("surface."):
        return _prove_surface_binding(appspec, eb, evidence, reasons)
    if eb.startswith("process."):
        pname = eb.split(".")[1] if "." in eb else ""
        rt_ok = _ensure_runtime(
            project_root, appspec, story, static_result, runtime_result, evidence, reasons
        )
        proc_ok = _prove_process_surfaces(appspec, pname, evidence, reasons)
        return rt_ok and proc_ok
    if eb.startswith("service."):
        if _ensure_runtime(
            project_root, appspec, story, static_result, runtime_result, evidence, reasons
        ):
            reasons.append("service_host_ready")
            return True
        return False
    if eb.lower().startswith("host_route "):
        reasons.append("host_route_static_only")
        evidence.append("host_route_bound")
        return True
    reasons.append(f"unsupported_binding:{eb}")
    return False


def journey_prove_one(
    project_root: Path,
    appspec: Any,
    story: Any,
    *,
    static_result: dict[str, Any],
    runtime_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Journey graph prove for one story."""
    base = {
        "story_id": story.story_id,
        "executed_by": static_result.get("executed_by"),
        "static": static_result,
        "evidence_kind": "journey",
        "evidence": list(static_result.get("evidence") or []),
    }
    static_res = str(static_result.get("result") or "")
    if static_res == "pass_static" and static_result.get("reason") == "narrative_only":
        return {
            **base,
            "result": "skip_journey",
            "reason": "narrative_only",
            "note": "Honesty mode — no journey path",
        }
    if not static_res.startswith("pass"):
        return {
            **base,
            "result": "skip_journey",
            "reason": "static_failed",
            "note": "Fix pass_static before journey prove",
        }

    eb = str(static_result.get("executed_by") or "")
    evidence = list(base["evidence"])
    reasons: list[str] = []
    ok = _dispatch_binding(
        project_root, appspec, story, eb, static_result, runtime_result, evidence, reasons
    )
    if ok and not reasons:
        reasons.append("journey_ok")

    return {
        **base,
        "result": "pass_journey" if ok else "fail_journey",
        "reason": ";".join(reasons) if reasons else ("journey_ok" if ok else "journey_failed"),
        "evidence": evidence,
        "note": (
            "Journey graph / hub shape evidence — not Playwright e2e. "
            "pass_journey means surfaces/hops/process targets are coherent."
        ),
    }


def prove_stories_journey(
    project_root: Path,
    appspec: Any,
    stories: list[Any],
    *,
    static_results: list[dict[str, Any]],
    runtime_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    by_id = {r["story_id"]: r for r in static_results}
    rt_by_id = {r["story_id"]: r for r in (runtime_results or [])}
    results = [
        journey_prove_one(
            project_root,
            appspec,
            s,
            static_result=by_id[s.story_id],
            runtime_result=rt_by_id.get(s.story_id),
        )
        for s in stories
    ]
    failed = [r for r in results if str(r.get("result", "")).startswith("fail")]
    skipped = [r for r in results if str(r.get("result", "")).startswith("skip")]
    passed = [r for r in results if str(r.get("result", "")).startswith("pass")]
    return {
        "ok": not failed,
        "operation": "prove",
        "evidence_kind": "journey",
        "checked": len(results),
        "passed": len(passed),
        "failed": len(failed),
        "skipped": len(skipped),
        "results": results,
        "note": (
            "pass_journey = surface hub/open-via graph coherent + process host ready. "
            "Not a browser e2e walk."
        ),
    }
