"""Load hyperpart scenario catalogue + scenario-driven opportunity rows.

Pairs with ``packages/hatchi-maxchi/docs/agent/hyperpart_scenarios.toml`` and
``docs/superpowers/specs/2026-08-07-hyperpart-emitter-scenario-cognition-design.md``.

Scanners implemented here are *small* heuristics that close residual gaps
the avatar/queue hardcode does not cover (e.g. planned switch emitter).
Catalogue rows with ``scanner = "catalogue_only"`` are agent documentation
until a scanner id is implemented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from dazzle.qa.hyperpart_types import HyperpartOpportunity

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover — py<3.11
    import tomli as tomllib  # type: ignore[no-redef]

REPO = Path(__file__).resolve().parents[3]
CATALOGUE_PATH = REPO / "packages" / "hatchi-maxchi" / "docs" / "agent" / "hyperpart_scenarios.toml"

_BOOL_KINDS = frozenset({"bool", "boolean"})
_SETTINGSISH = re.compile(
    r"(setting|preference|pref|notif|mute|enable|disable|opt[_-]?in|opt[_-]?out)",
    re.I,
)
_FIELD_SETTINGSISH = re.compile(
    r"(enabled|disabled|active|muted|notify|notification|opt_in|opt_out|is_)",
    re.I,
)


@dataclass(frozen=True)
class Scenario:
    """One catalogue row."""

    id: str
    hyperpart: str
    authoring: str
    layer: str
    job: str
    use_when: tuple[str, ...]
    refuse_when: tuple[str, ...]
    status_if_fit: str
    ownership: str
    severity: str
    residual_lane: str
    example_homes: tuple[str, ...]
    scanner: str

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hyperpart": self.hyperpart,
            "authoring": self.authoring,
            "layer": self.layer,
            "job": self.job,
            "use_when": list(self.use_when),
            "refuse_when": list(self.refuse_when),
            "status_if_fit": self.status_if_fit,
            "ownership": self.ownership,
            "severity": self.severity,
            "residual_lane": self.residual_lane,
            "example_homes": list(self.example_homes),
            "scanner": self.scanner,
        }


def _str_tuple(raw: Any) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(str(x) for x in raw)


def _scenario_from_raw(raw: dict[str, Any]) -> Scenario | None:
    sid = str(raw.get("id") or "").strip()
    if not sid:
        return None
    return Scenario(
        id=sid,
        hyperpart=str(raw.get("hyperpart") or "").strip(),
        authoring=str(raw.get("authoring") or "").strip(),
        layer=str(raw.get("layer") or "").strip(),
        job=str(raw.get("job") or "").strip(),
        use_when=_str_tuple(raw.get("use_when")),
        refuse_when=_str_tuple(raw.get("refuse_when")),
        status_if_fit=str(raw.get("status_if_fit") or "author_action").strip(),
        ownership=str(raw.get("ownership") or "product").strip(),
        severity=str(raw.get("severity") or "medium").strip(),
        residual_lane=str(raw.get("residual_lane") or "none").strip(),
        example_homes=_str_tuple(raw.get("example_homes")),
        scanner=str(raw.get("scanner") or "catalogue_only").strip(),
    )


@lru_cache(maxsize=1)
def load_scenarios(path: Path | None = None) -> tuple[Scenario, ...]:
    """Parse catalogue TOML (cached)."""
    p = path or CATALOGUE_PATH
    if not p.is_file():
        return ()
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    rows: list[Scenario] = []
    for raw in list(data.get("scenario") or []):
        if isinstance(raw, dict):
            sc = _scenario_from_raw(raw)
            if sc is not None:
                rows.append(sc)
    return tuple(rows)


def scenarios_by_scanner(scanner_id: str) -> list[Scenario]:
    return [s for s in load_scenarios() if s.scanner == scanner_id]


def catalogue_snapshot() -> dict[str, Any]:
    """Agent-facing cognition: all scenarios + counts by residual_lane."""
    rows = load_scenarios()
    by_lane: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_hp: dict[str, int] = {}
    for s in rows:
        by_lane[s.residual_lane] = by_lane.get(s.residual_lane, 0) + 1
        by_status[s.status_if_fit] = by_status.get(s.status_if_fit, 0) + 1
        by_hp[s.hyperpart] = by_hp.get(s.hyperpart, 0) + 1
    return {
        "schema_version": 1,
        "path": str(CATALOGUE_PATH.relative_to(REPO)) if CATALOGUE_PATH.is_file() else None,
        "count": len(rows),
        "by_residual_lane": by_lane,
        "by_status_if_fit": by_status,
        "by_hyperpart": by_hp,
        "scenarios": [s.to_json() for s in rows],
        "doctrine": (
            "docs/superpowers/specs/2026-08-07-hyperpart-emitter-scenario-cognition-design.md"
        ),
    }


def _field_type_kind(ft: Any) -> str:
    kind = getattr(ft, "kind", None)
    if kind is None:
        return ""
    return str(getattr(kind, "value", kind) or "").lower()


def _surface_mode(surface: Any) -> str:
    return str(
        getattr(getattr(surface, "mode", None), "value", getattr(surface, "mode", "")) or ""
    ).lower()


def _entity_by_name(appspec: Any) -> dict[str, Any]:
    domain = getattr(appspec, "domain", None)
    entities = list(getattr(domain, "entities", None) or []) if domain else []
    return {str(getattr(e, "name", "") or ""): e for e in entities}


def _is_bool_kind(kind: str) -> bool:
    k = (kind or "").lower()
    return k in _BOOL_KINDS or k == "bool" or k.endswith(".bool")


def _surface_field_widget(surface: Any, field_name: str) -> str:
    """Return author ``widget=`` for a field on a surface, if declared."""
    for section in list(getattr(surface, "sections", None) or []):
        for el in list(getattr(section, "elements", None) or []):
            fn = str(getattr(el, "field_name", "") or getattr(el, "name", "") or "")
            if fn != field_name:
                continue
            # options dict from parser: field ... widget=switch
            opts = getattr(el, "options", None) or getattr(el, "field_options", None) or {}
            if isinstance(opts, dict):
                w = opts.get("widget") or opts.get("Widget")
                if w:
                    return str(w).strip().lower()
            w2 = getattr(el, "widget", None)
            if w2:
                return str(w2).strip().lower()
    return ""


def _surface_field_names(surface: Any) -> list[str]:
    names: list[str] = []
    for section in list(getattr(surface, "sections", None) or []):
        for el in list(getattr(section, "elements", None) or []):
            fn = str(getattr(el, "field_name", "") or getattr(el, "name", "") or "")
            if fn:
                names.append(fn)
    return names


def _switch_emit_covered(sc: Scenario, ent: str, fn: str, surface: str) -> HyperpartOpportunity:
    return HyperpartOpportunity(
        hyperpart=sc.hyperpart,
        kind=f"scenario:{sc.id}",
        entity=ent,
        field=fn,
        surface=surface,
        location=f"surface:{surface}.field:{fn}",
        status="emit_covered",
        severity="low",
        description=(
            f"{ent}.{fn} on {surface} declares widget=switch — "
            f"framework emits HM Switch (data-dz-switch)."
        ),
        ownership="framework",
        notes=f"scenario={sc.id} widget=switch lane={sc.residual_lane}",
        hosts="field",
    )


def _switch_author_action(
    sc: Scenario, ent: str, fn: str, surface: str, widget: str
) -> HyperpartOpportunity:
    return HyperpartOpportunity(
        hyperpart=sc.hyperpart,
        kind=f"scenario:{sc.id}",
        entity=ent,
        field=fn,
        surface=surface,
        location=f"surface:{surface}.field:{fn}",
        status="author_action",
        severity=sc.severity,
        description=(
            f"{ent}.{fn} on {surface} looks like a boolean settings flag — "
            f"prefer widget=switch (scenario {sc.id!r})."
        ),
        ownership="product",
        notes=f"scenario={sc.id} widget={widget or '-'} lane={sc.residual_lane}",
        hosts="field",
    )


def _is_bookkeeping_bool(fn: str) -> bool:
    """Audit / system flags that must not be switch author_action residual.

    ``notification_sent`` (FeedbackReport toast idempotency) matches the
    loose ``notification`` settings-like regex but is not a preferences UI
    control — refuse those suffixes so headless platform fields do not
    thrash example-apps residual.
    """
    fl = fn.lower()
    if fl in ("selected", "checked"):
        return True
    if fl.endswith(("_ids", "_sent", "_acked", "_seen", "_count")):
        return True
    return False


# Explicit form widgets that already author a non-checkbox control. These are
# not "missing switch" residual — e.g. mode_press ``widget=toggle`` on
# is_starred (catalogue example_homes) must not thrash boolean_settings_switch.
_SWITCH_ALT_WIDGETS = frozenset(
    {
        "toggle",
        "toggle_group",
        "radio",
        "select",
        "combobox",
        "tags",
        "rich_text",
        "picker",
        "slider",
        "textarea",
    }
)


def _switch_row_for_field(
    *,
    sc: Scenario,
    ent_name: str,
    fn: str,
    sname: str,
    widget: str,
    formish: bool,
    surface_settings: bool,
) -> HyperpartOpportunity | None:
    """Build one switch opportunity or None if field is out of scope."""
    if widget == "switch":
        return _switch_emit_covered(sc, ent_name, fn, sname)
    # Already authored to a different form hyperpart (toggle dogfood, etc.).
    if widget in _SWITCH_ALT_WIDGETS:
        return None
    # Form control only — skip list/view columns that merely *name* like settings.
    if not formish and not surface_settings:
        return None
    if _is_bookkeeping_bool(fn):
        return None
    # Require a settings signal — bare formish must not flag every create bool
    # (that flooded FeedbackReport.notification_sent as product residual).
    if not (_FIELD_SETTINGSISH.search(fn) or surface_settings):
        return None
    return _switch_author_action(sc, ent_name, fn, sname, widget)


def _iter_bool_fields(surface: Any, entity: Any) -> list[tuple[str, Any]]:
    field_map = {str(f.name): f for f in list(getattr(entity, "fields", None) or [])}
    surface_names = _surface_field_names(surface)
    if surface_names:
        candidates = surface_names
    elif bool(getattr(surface, "headless", False)):
        # Headless API surfaces (e.g. feedback_create) list no sections —
        # do not invent authoring targets from the whole entity map.
        candidates = []
    else:
        candidates = list(field_map.keys())
    out: list[tuple[str, Any]] = []
    for fn in candidates:
        fspec = field_map.get(fn)
        if fspec and _is_bool_kind(_field_type_kind(getattr(fspec, "type", None))):
            out.append((fn, fspec))
    return out


def _skip_switch_authoring(*, domain: str, headless: bool, widget: str) -> bool:
    """True when only explicit widget=switch coverage is allowed (no author_action).

    Platform-injected entities and headless API surfaces must not thrash
    example-apps residual with product adopt rows for system bools.
    """
    if widget == "switch":
        return False
    return domain == "platform" or headless


def scan_boolean_switch(appspec: Any) -> list[Any]:
    """Boolean settings-like fields → switch scenario residual.

    After the SwitchField emitter ships:
    - ``widget=switch`` on the surface field → ``emit_covered``
    - settings-like bool without widget → ``author_action`` (product adopt)
    """
    scenarios = scenarios_by_scanner("boolean_switch") or scenarios_by_scanner(
        "boolean_switch_planned"
    )
    if not scenarios:
        return []
    sc = scenarios[0]
    out: list[Any] = []
    entity_by_name = _entity_by_name(appspec)
    seen: set[tuple[str, str, str]] = set()

    for surface in list(getattr(appspec, "surfaces", None) or []):
        sname = str(getattr(surface, "name", "") or "")
        mode = _surface_mode(surface)
        surface_settings = bool(_SETTINGSISH.search(sname))
        formish = mode in ("create", "edit", "form", "settings")
        headless = bool(getattr(surface, "headless", False))
        ent_name = str(
            getattr(surface, "entity_ref", None) or getattr(surface, "entity", None) or ""
        )
        entity = entity_by_name.get(ent_name)
        if not entity:
            continue
        domain = str(getattr(entity, "domain", "") or "")
        for fn, _fspec in _iter_bool_fields(surface, entity):
            key = (ent_name, fn, sname)
            if key in seen:
                continue
            widget = _surface_field_widget(surface, fn)
            if _skip_switch_authoring(domain=domain, headless=headless, widget=widget):
                continue
            row = _switch_row_for_field(
                sc=sc,
                ent_name=ent_name,
                fn=fn,
                sname=sname,
                widget=widget,
                formish=formish,
                surface_settings=surface_settings,
            )
            if row is None:
                continue
            seen.add(key)
            out.append(row)
    return out


# Alias for callers/tests that still import the planned name
scan_boolean_switch_planned = scan_boolean_switch


def scan_scenario_opportunities(appspec: Any) -> list[Any]:
    """All implemented scenario scanners."""
    rows: list[Any] = []
    rows.extend(scan_boolean_switch(appspec))
    return rows
