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
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from dazzle.render.user_chip import looks_like_person_ref

# Workspace display modes that already pull rich hyperparts.
_QUEUE_ISH_NAME = re.compile(
    r"(overdue|inbox|queue|backlog|urgent|assigned.?to.?me|my.?work)",
    re.I,
)


@dataclass
class HyperpartOpportunity:
    """One place a hyperpart should be considered or is now default-emitted."""

    hyperpart: str  # avatar | queue | badge | money | …
    kind: str  # person_ref | work_queue | …
    entity: str
    field: str
    surface: str
    location: str  # human path, e.g. surface TaskList.field.assigned_to
    status: str  # default_emit | author_action | verify
    severity: str  # low | medium | high
    description: str
    ownership: str = "framework"  # framework default vs product authoring
    notes: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_friction(self) -> dict[str, Any]:
        return {
            "category": "missing" if self.status == "author_action" else "other",
            "severity": self.severity,
            "description": self.description,
            "url": self.location,
            "evidence": (
                f"hyperpart={self.hyperpart} kind={self.kind} "
                f"entity={self.entity}.{self.field} status={self.status} {self.notes}"
            ),
            "blocks_pilot": False,
            "ownership": self.ownership,
        }


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


def scan_person_ref_opportunities(appspec: Any) -> list[HyperpartOpportunity]:
    """Every person-like ref on a list/detail surface field."""
    out: list[HyperpartOpportunity] = []
    domain = getattr(appspec, "domain", None)
    entities = list(getattr(domain, "entities", None) or []) if domain else []
    entity_by_name = {str(getattr(e, "name", "") or ""): e for e in entities}

    for surface in list(getattr(appspec, "surfaces", None) or []):
        sname = str(getattr(surface, "name", "") or "")
        ent_name = str(
            getattr(surface, "entity_ref", None) or getattr(surface, "entity", None) or ""
        )
        entity = entity_by_name.get(ent_name)
        if not entity:
            continue
        field_map = {str(f.name): f for f in list(getattr(entity, "fields", None) or [])}
        mode = str(
            getattr(getattr(surface, "mode", None), "value", getattr(surface, "mode", "")) or ""
        ).lower()
        # Walk declared sections/elements; fall back to all entity fields for list/view.
        names: list[str] = []
        for section in list(getattr(surface, "sections", None) or []):
            for el in list(getattr(section, "elements", None) or []):
                fn = str(getattr(el, "field_name", "") or "")
                if fn:
                    names.append(fn)
        # Avatar chip is a list/detail cell default — skip create/edit form fields
        # (those stay search-select widgets).
        if any(x in mode for x in ("create", "edit", "form")):
            continue
        if not names and ("list" in mode or "view" in mode or "detail" in mode or mode == ""):
            names = [str(f.name) for f in field_map.values()]

        seen: set[str] = set()
        for fn in names:
            if fn in seen:
                continue
            seen.add(fn)
            fspec = field_map.get(fn)
            if not fspec:
                continue
            ft = getattr(fspec, "type", None)
            kind = _field_type_kind(ft)
            if kind not in ("ref", "belongs_to"):
                continue
            ref_ent = _ref_entity(ft)
            if not _is_person_ref(fn, ref_ent):
                continue
            loc = f"surface:{sname}.field:{fn}"
            out.append(
                HyperpartOpportunity(
                    hyperpart="avatar",
                    kind="person_ref",
                    entity=ent_name,
                    field=fn,
                    surface=sname,
                    location=loc,
                    status="default_emit",
                    severity="low",
                    description=(
                        f"{ent_name}.{fn} is a person ref ({ref_ent or 'heuristic'}) — "
                        f"framework emits Avatar chip (dz-avatar) by default in list/detail cells."
                    ),
                    ownership="framework",
                    notes="user_chip default; opt-out via column avatar:false",
                )
            )
    return out


def scan_queue_opportunities(appspec: Any) -> list[HyperpartOpportunity]:
    """Workspaces/regions named like queues that still use plain list display."""
    out: list[HyperpartOpportunity] = []
    for ws in list(getattr(appspec, "workspaces", None) or []):
        wname = str(getattr(ws, "name", "") or "")
        for region in list(getattr(ws, "regions", None) or []):
            rname = str(getattr(region, "name", "") or "")
            title = str(getattr(region, "title", "") or "")
            display = str(
                getattr(getattr(region, "display", None), "value", getattr(region, "display", ""))
                or ""
            ).lower()
            # Match region name/title only — not the parent workspace name
            # (my_work/* was falsely flagging every region as a work queue).
            blob = f"{rname} {title}"
            if not _QUEUE_ISH_NAME.search(blob):
                continue
            if "queue" in display or "kanban" in display or "task_inbox" in display:
                continue
            if display in ("", "list", "table", "none"):
                out.append(
                    HyperpartOpportunity(
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
                )
    return out


def scan_appspec(appspec: Any) -> list[HyperpartOpportunity]:
    """All static hyperpart opportunities for one app."""
    rows = scan_person_ref_opportunities(appspec)
    rows.extend(scan_queue_opportunities(appspec))
    return rows


def build_opportunity_report(
    *,
    app: str,
    opportunities: list[HyperpartOpportunity],
) -> dict[str, Any]:
    from dazzle.qa.trial_friction import is_auto_seed_eligible, normalize_friction_entry

    frictions = [normalize_friction_entry(o.to_friction()) for o in opportunities]
    # Only author_action product rows seed improve PENDING.
    auto_seed = [
        f
        for f, o in zip(frictions, opportunities, strict=True)
        if o.status == "author_action" and is_auto_seed_eligible(f)
    ]
    by_hp: dict[str, int] = {}
    for o in opportunities:
        by_hp[o.hyperpart] = by_hp.get(o.hyperpart, 0) + 1
    return {
        "schema_version": 1,
        "mode": "hyperpart_opportunity",
        "app": app,
        "count": len(opportunities),
        "by_hyperpart": by_hp,
        "opportunities": [o.to_json() for o in opportunities],
        "friction": frictions,
        "auto_seed": auto_seed,
        "guidance": {
            "avatar": (
                "If displaying a reference to a real person who is a system user "
                "(or Contact/assignee-like entity), use the Avatar hyperpart chip. "
                "Framework default: list/detail ref cells emit .dz-avatar + name."
            ),
            "queue": ("Urgency-ordered work of the same type → display: queue, not a plain list."),
            "badge": "Lifecycle / status enums already map to badge cells by default.",
            "money": "Money fields map to currency cells by default.",
        },
    }
