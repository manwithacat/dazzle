"""Static hyperpart *opportunity* scan for example apps.

Unlike fleet coverage (is Avatar exercised *somewhere*) and gallery
coherence (does the part look good in isolation), this scan asks:

  "Given this app's DSL, where should a hyperpart be applied by default?"

Primary rule (agent + framework shared):

  If a list/detail field is a ``ref`` to a person-like entity (User, Contact, …)
  or a person-named FK (``assigned_to``, ``author``, …), prefer the **Avatar**
  hyperpart chip — framework emit is default via ``dazzle.render.user_chip``.

Emits opportunity rows + trial-friction-compatible ``auto_seed`` candidates
(``category=missing`` for under-application that still needs author action).

Scenario catalogue (jobs → hyperpart → authoring class):
``packages/hatchi-maxchi/docs/agent/hyperpart_scenarios.toml`` via
``dazzle.qa.hyperpart_scenarios``. Doctrine:
``docs/superpowers/specs/2026-08-07-hyperpart-emitter-scenario-cognition-design.md``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.qa.hyperpart_scenarios import catalogue_snapshot, scan_scenario_opportunities
from dazzle.qa.hyperpart_types import HyperpartOpportunity
from dazzle.qa.trial_friction import is_auto_seed_eligible, normalize_friction_entry
from dazzle.render.user_chip import looks_like_person_ref

# Re-export for callers/tests that import from this module.
__all__ = [
    "HyperpartOpportunity",
    "build_opportunity_report",
    "scan_appspec",
    "scan_person_ref_opportunities",
    "scan_person_timeline_meta_opportunities",
    "scan_queue_opportunities",
]

# Workspace display modes that already pull rich hyperparts.
_QUEUE_ISH_NAME = re.compile(
    r"(overdue|inbox|queue|backlog|urgent|assigned.?to.?me|my.?work)",
    re.I,
)
_FORM_MODES = ("create", "edit", "form")
_LISTISH_MODES = ("list", "view", "detail", "")
_QUEUE_DISPLAYS = ("queue", "kanban", "task_inbox")
_PLAIN_DISPLAYS = ("", "list", "table", "none")
_REF_KINDS = frozenset({"ref", "belongs_to"})


def _field_type_kind(ft: Any) -> str:
    kind = getattr(ft, "kind", None)
    if kind is None:
        return ""
    return str(getattr(kind, "value", kind) or "").lower()


def _ref_entity(ft: Any) -> str:
    return str(getattr(ft, "ref_entity", None) or "").strip()


def _is_person_ref(field_name: str, ref_entity: str) -> bool:
    col = {"key": field_name, "ref_entity": ref_entity, "filter_ref_entity": ref_entity}
    # Value stub so looks_like_person_ref can use entity/key heuristics.
    return looks_like_person_ref({"name": "probe"}, col)


def _surface_mode(surface: Any) -> str:
    return str(
        getattr(getattr(surface, "mode", None), "value", getattr(surface, "mode", "")) or ""
    ).lower()


def _section_field_names(surface: Any) -> list[str]:
    names: list[str] = []
    for section in list(getattr(surface, "sections", None) or []):
        for el in list(getattr(section, "elements", None) or []):
            fn = str(getattr(el, "field_name", "") or "")
            if fn:
                names.append(fn)
    return names


def _entity_by_name(appspec: Any) -> dict[str, Any]:
    domain = getattr(appspec, "domain", None)
    entities = list(getattr(domain, "entities", None) or []) if domain else []
    return {str(getattr(e, "name", "") or ""): e for e in entities}


def _person_ref_for_field(
    *,
    fn: str,
    field_map: dict[str, Any],
    ent_name: str,
    sname: str,
) -> HyperpartOpportunity | None:
    fspec = field_map.get(fn)
    if not fspec:
        return None
    ft = getattr(fspec, "type", None)
    if _field_type_kind(ft) not in _REF_KINDS:
        return None
    ref_ent = _ref_entity(ft)
    if not _is_person_ref(fn, ref_ent):
        return None
    return HyperpartOpportunity(
        hyperpart="avatar",
        kind="person_ref",
        entity=ent_name,
        field=fn,
        surface=sname,
        location=f"surface:{sname}.field:{fn}",
        status="emit_covered",
        severity="low",
        description=(
            f"{ent_name}.{fn} is a person ref ({ref_ent or 'heuristic'}) — "
            f"framework emits Avatar on list/detail cells (presentation matrix)."
        ),
        ownership="framework",
        notes="user_chip / present(); opt-out via column avatar:false",
        hosts="list_cell,detail_cell",
    )


def _field_names_for_surface(surface: Any, field_map: dict[str, Any], mode: str) -> list[str]:
    names = _section_field_names(surface)
    if names:
        return names
    if any(token in mode for token in _LISTISH_MODES if token) or mode == "":
        return [str(f.name) for f in field_map.values()]
    return names


def scan_person_ref_opportunities(appspec: Any) -> list[HyperpartOpportunity]:
    """Every person-like ref on a list/detail surface field."""
    out: list[HyperpartOpportunity] = []
    entity_by_name = _entity_by_name(appspec)

    for surface in list(getattr(appspec, "surfaces", None) or []):
        sname = str(getattr(surface, "name", "") or "")
        ent_name = str(
            getattr(surface, "entity_ref", None) or getattr(surface, "entity", None) or ""
        )
        entity = entity_by_name.get(ent_name)
        if not entity:
            continue
        mode = _surface_mode(surface)
        # Avatar chip is a list/detail cell default — skip create/edit form fields.
        if any(x in mode for x in _FORM_MODES):
            continue
        field_map = {str(f.name): f for f in list(getattr(entity, "fields", None) or [])}
        names = _field_names_for_surface(surface, field_map, mode)
        seen: set[str] = set()
        for fn in names:
            if fn in seen:
                continue
            seen.add(fn)
            row = _person_ref_for_field(fn=fn, field_map=field_map, ent_name=ent_name, sname=sname)
            if row is not None:
                out.append(row)
    return out


def _region_display(region: Any) -> str:
    return str(
        getattr(getattr(region, "display", None), "value", getattr(region, "display", "")) or ""
    ).lower()


def _queue_opportunity(
    *, wname: str, region: Any, rname: str, display: str
) -> HyperpartOpportunity | None:
    title = str(getattr(region, "title", "") or "")
    # Match region name/title only — not the parent workspace name
    # (my_work/* was falsely flagging every region as a work queue).
    if not _QUEUE_ISH_NAME.search(f"{rname} {title}"):
        return None
    if any(token in display for token in _QUEUE_DISPLAYS):
        return None
    if display not in _PLAIN_DISPLAYS:
        return None
    return HyperpartOpportunity(
        hyperpart="queue",
        kind="work_queue",
        entity=str(getattr(region, "source", "") or ""),
        field=rname,
        surface=wname,
        location=f"workspace:{wname}.region:{rname}",
        status="author_action",
        severity="medium",
        description=(
            f"Region {wname}/{rname} looks like a work queue "
            f"(display={display or 'list'}) — consider display: queue."
        ),
        ownership="product",
        notes="semantic opportunity; not auto-emitted",
    )


def scan_queue_opportunities(appspec: Any) -> list[HyperpartOpportunity]:
    """Workspaces/regions named like queues that still use plain list display."""
    out: list[HyperpartOpportunity] = []
    for ws in list(getattr(appspec, "workspaces", None) or []):
        wname = str(getattr(ws, "name", "") or "")
        for region in list(getattr(ws, "regions", None) or []):
            rname = str(getattr(region, "name", "") or "")
            row = _queue_opportunity(
                wname=wname, region=region, rname=rname, display=_region_display(region)
            )
            if row is not None:
                out.append(row)
    return out


def scan_person_queue_meta_opportunities(appspec: Any) -> list[HyperpartOpportunity]:
    """Person refs on ``display: queue`` regions — presentation matrix host.

    Status is ``emit_covered`` when framework ``present(person, queue_meta)``
    is live (Avatar chip, no Assigned To prose). Host honesty: do not claim
    full green for person refs that only cover list/detail.
    """
    out: list[HyperpartOpportunity] = []
    entity_by_name = _entity_by_name(appspec)
    for ws in list(getattr(appspec, "workspaces", None) or []):
        wname = str(getattr(ws, "name", "") or "")
        for region in list(getattr(ws, "regions", None) or []):
            if _region_display(region) != "queue":
                continue
            rname = str(getattr(region, "name", "") or "")
            ent_name = str(getattr(region, "source", None) or getattr(region, "entity", "") or "")
            entity = entity_by_name.get(ent_name)
            if not entity:
                continue
            field_map = {str(f.name): f for f in list(getattr(entity, "fields", None) or [])}
            for fn, fspec in field_map.items():
                ft = getattr(fspec, "type", None)
                if _field_type_kind(ft) not in _REF_KINDS:
                    continue
                ref_ent = _ref_entity(ft)
                if not _is_person_ref(fn, ref_ent):
                    continue
                out.append(
                    HyperpartOpportunity(
                        hyperpart="avatar",
                        kind="person_ref_queue_meta",
                        entity=ent_name,
                        field=fn,
                        surface=wname,
                        location=f"workspace:{wname}.region:{rname}.field:{fn}",
                        status="emit_covered",
                        severity="low",
                        description=(
                            f"{ent_name}.{fn} on queue {wname}/{rname} — "
                            f"presentation matrix emits Avatar (queue_meta), "
                            f"not 'Assigned To: <text>' prose."
                        ),
                        ownership="framework",
                        notes="present(person, queue_meta) → avatar_only",
                        hosts="queue_meta",
                    )
                )
    return out


_TIMELINE_DISPLAYS = frozenset({"activity_feed", "timeline"})


def _timeline_person_opportunity(
    *,
    wname: str,
    rname: str,
    display: str,
    ent_name: str,
    fn: str,
    fspec: Any,
) -> HyperpartOpportunity | None:
    ft = getattr(fspec, "type", None)
    if _field_type_kind(ft) not in _REF_KINDS:
        return None
    ref_ent = _ref_entity(ft)
    if not _is_person_ref(fn, ref_ent):
        return None
    return HyperpartOpportunity(
        hyperpart="avatar",
        kind="person_ref_timeline_meta",
        entity=ent_name,
        field=fn,
        surface=wname,
        location=f"workspace:{wname}.region:{rname}.field:{fn}",
        status="emit_covered",
        severity="low",
        description=(
            f"{ent_name}.{fn} on {display} {wname}/{rname} — "
            f"presentation matrix emits Avatar (timeline_meta), not actor prose."
        ),
        ownership="framework",
        notes="present(person, timeline_meta) → avatar_name",
        hosts="timeline_meta",
    )


def scan_person_timeline_meta_opportunities(appspec: Any) -> list[HyperpartOpportunity]:
    """Person refs on ``display: activity_feed`` / ``timeline`` — timeline_meta host.

    Status is ``emit_covered`` when framework ``present(person, timeline_meta)``
    is live (Avatar chip). Scalar leftover actors stay escaped text.
    """
    out: list[HyperpartOpportunity] = []
    entity_by_name = _entity_by_name(appspec)
    for ws in list(getattr(appspec, "workspaces", None) or []):
        wname = str(getattr(ws, "name", "") or "")
        for region in list(getattr(ws, "regions", None) or []):
            display = _region_display(region)
            if display not in _TIMELINE_DISPLAYS:
                continue
            rname = str(getattr(region, "name", "") or "")
            ent_name = str(getattr(region, "source", None) or getattr(region, "entity", "") or "")
            entity = entity_by_name.get(ent_name)
            if not entity:
                continue
            field_map = {str(f.name): f for f in list(getattr(entity, "fields", None) or [])}
            for fn, fspec in field_map.items():
                row = _timeline_person_opportunity(
                    wname=wname,
                    rname=rname,
                    display=display,
                    ent_name=ent_name,
                    fn=fn,
                    fspec=fspec,
                )
                if row is not None:
                    out.append(row)
    return out


def scan_appspec(appspec: Any) -> list[HyperpartOpportunity]:
    """All static hyperpart opportunities for one app."""
    rows = scan_person_ref_opportunities(appspec)
    rows.extend(scan_person_queue_meta_opportunities(appspec))
    rows.extend(scan_person_timeline_meta_opportunities(appspec))
    rows.extend(scan_queue_opportunities(appspec))
    rows.extend(scan_scenario_opportunities(appspec))
    return rows


_GUIDANCE = {
    "avatar": (
        "Role person → Avatar via presentation matrix (list/detail + queue_meta + timeline_meta). "
        "Doctrine: docs/reference/hyperpart-presentation.md. "
        "Statuses: emit_covered (all listed hosts), emit_partial (some hosts), "
        "never treat list-only chip as full green while queue_meta stringifies."
    ),
    "queue": "Urgency-ordered work of the same type → display: queue, not a plain list.",
    "badge": "Lifecycle / status enums already map to badge cells by default.",
    "money": "Money fields map to currency cells by default.",
    "switch": (
        "Boolean settings → widget=switch → SwitchField / data-dz-switch (HM Switch). "
        "Default bool still checkbox; authors opt in. Scenario residual: "
        "emit_covered when widget present, author_action when settings-like bool lacks it. "
        "Doctrine: hyperpart-emitter-scenario-cognition design (2026-08-07)."
    ),
    "scenarios": (
        "Full job→hyperpart catalogue: packages/hatchi-maxchi/docs/agent/hyperpart_scenarios.toml. "
        "One authoring surface per job; density via present() matrix, not extra display: verbs."
    ),
}


def _residual_counts(
    opportunities: list[HyperpartOpportunity],
) -> tuple[dict[str, int], dict[str, int], dict[str, int], int, int]:
    by_hp: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_lane: dict[str, int] = {}
    planned = 0
    author_action = 0
    for o in opportunities:
        by_hp[o.hyperpart] = by_hp.get(o.hyperpart, 0) + 1
        by_status[o.status] = by_status.get(o.status, 0) + 1
        if o.status == "planned_emitter":
            planned += 1
            by_lane["framework-ux"] = by_lane.get("framework-ux", 0) + 1
        elif o.status == "author_action":
            author_action += 1
            lane = "example-apps" if o.ownership == "product" else "framework-ux"
            by_lane[lane] = by_lane.get(lane, 0) + 1
    return by_hp, by_status, by_lane, planned, author_action


def _force_lane(planned: int, author_action: int) -> str | None:
    if planned > 0 and author_action == 0:
        return "framework-ux"
    if author_action > 0:
        return "example-apps"
    return None


def build_opportunity_report(
    *,
    app: str,
    opportunities: list[HyperpartOpportunity],
) -> dict[str, Any]:
    from dazzle.render.presentation import cognition_snapshot

    frictions = [normalize_friction_entry(o.to_friction()) for o in opportunities]
    # Only author_action product rows seed improve PENDING.
    auto_seed = [
        f
        for f, o in zip(frictions, opportunities, strict=True)
        if o.status == "author_action" and is_auto_seed_eligible(f)
    ]
    by_hp, by_status, by_lane, planned, author_action = _residual_counts(opportunities)
    cog = cognition_snapshot()
    person_rows = [o for o in opportunities if o.kind.startswith("person")]
    all_scanned_green = bool(person_rows) and all(o.status == "emit_covered" for o in person_rows)
    scenarios = catalogue_snapshot()
    caveat = (
        "emit_covered applies only to hosts_audited_by_scanner. "
        "hosts_not_yet_audited may still stringify on stills — open hero PNG. "
        "planned_emitter rows need framework emitters before example adopt."
        if all_scanned_green
        else "Drain author_action / emit_partial / matrix_miss / planned_emitter first; then stills."
    )
    return {
        "schema_version": 3,
        "mode": "hyperpart_opportunity",
        "app": app,
        "count": len(opportunities),
        "by_hyperpart": by_hp,
        "by_status": by_status,
        "residual": {
            "author_action": author_action,
            "planned_emitter": planned,
            "by_lane": by_lane,
            "force_lane": _force_lane(planned, author_action),
        },
        "opportunities": [o.to_json() for o in opportunities],
        "friction": frictions,
        "auto_seed": auto_seed,
        "guidance": dict(_GUIDANCE),
        "scenario_catalogue": {
            "count": scenarios.get("count"),
            "by_residual_lane": scenarios.get("by_residual_lane"),
            "by_status_if_fit": scenarios.get("by_status_if_fit"),
            "doctrine": scenarios.get("doctrine"),
            "path": scenarios.get("path"),
        },
        "presentation_cognition": {
            **cog,
            "person_rows_all_emit_covered": all_scanned_green,
            "caveat": caveat,
        },
    }


def _write_opportunity_report(
    report: dict[str, Any],
    project_dir: Path,
    *,
    output: Path | None,
    stdout_only: bool,
    echo: Callable[..., Any],
) -> None:
    payload = json.dumps(report, indent=2, default=str) + "\n"
    if stdout_only:
        echo(payload, nl=False)
        return
    out = Path(output) if output is not None else None
    if out is None:
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        docs = project_dir / "dev_docs"
        docs.mkdir(parents=True, exist_ok=True)
        out = docs / f"qa-hyperpart-opportunities-{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload, encoding="utf-8")
    rel: Path | str = out
    try:
        rel = out.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        pass
    echo(f"Wrote {rel}")


def _echo_opportunity_summary(
    report: dict[str, Any],
    opportunities: list[HyperpartOpportunity],
    *,
    app_name: str,
    as_table: bool,
    stdout_only: bool,
    echo: Callable[..., Any],
) -> None:
    n = int(report.get("count") or 0)
    n_seed = len(report.get("auto_seed") or [])
    by_hp = report.get("by_hyperpart") or {}
    hp_bits = " ".join(f"{k}={v}" for k, v in sorted(by_hp.items()))
    summary = f"hyperpart-opportunities app={app_name} count={n} auto_seed={n_seed}"
    if hp_bits:
        summary = f"{summary} {hp_bits}"
    if as_table:
        echo(summary)
        for o in opportunities:
            echo(f"  [{o.status}/{o.severity}] {o.hyperpart} {o.location} — {o.description[:100]}")
        return
    echo(summary, err=stdout_only)


def run_hyperpart_opportunities(
    project_dir: Path | str,
    *,
    as_table: bool = False,
    output: Path | str | None = None,
    stdout_only: bool = False,
    fail_on_product: bool = False,
    echo: Callable[..., Any] = print,
    exit_fn: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """CLI body for ``dazzle qa hyperpart-opportunities`` (kept out of qa.py for MI)."""
    project_dir = Path(project_dir)
    try:
        appspec = load_project_appspec(project_dir)
    except Exception as exc:
        echo(f"Failed to load AppSpec: {exc}", err=True)
        if exit_fn is not None:
            exit_fn(1)
        raise

    app_name = str(getattr(appspec, "name", None) or project_dir.name)
    opportunities = scan_appspec(appspec)
    report = build_opportunity_report(app=app_name, opportunities=opportunities)
    _write_opportunity_report(
        report,
        project_dir,
        output=Path(output) if output is not None else None,
        stdout_only=stdout_only,
        echo=echo,
    )
    _echo_opportunity_summary(
        report,
        opportunities,
        app_name=app_name,
        as_table=as_table,
        stdout_only=stdout_only,
        echo=echo,
    )
    if fail_on_product and report.get("auto_seed") and exit_fn is not None:
        exit_fn(1)
    return report
