"""Classify an AppSpec against the representation ladder (#1617)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.db.verify import unanchored_invariant_fields
from dazzle.representation.patterns import PatternId


def _kind(field: Any) -> str:
    t = getattr(field, "type", None)
    k = getattr(t, "kind", None)
    return str(getattr(k, "value", k) or "")


def _field_names(entity: Any) -> set[str]:
    return {str(f.name) for f in getattr(entity, "fields", None) or []}


def _optional_ref_fields(entity: Any) -> list[str]:
    out: list[str] = []
    for f in getattr(entity, "fields", None) or []:
        if _kind(f) not in ("ref", "belongs_to"):
            continue
        if getattr(f, "is_required", False):
            continue
        out.append(str(f.name))
    return out


def _exclusive_sets_from_invariants(entity: Any) -> list[list[str]]:
    sets: list[list[str]] = []
    for inv in getattr(entity, "invariants", None) or []:
        fields = unanchored_invariant_fields(inv)
        if fields and len(fields) >= 2:
            sets.append(list(fields))
    return sets


def _hand_rolled_poly_pairs(entity: Any) -> list[dict[str, str]]:
    names = _field_names(entity)
    kinds = {str(f.name): _kind(f) for f in getattr(entity, "fields", None) or []}
    poly_names = {
        str(f.name) for f in getattr(entity, "fields", None) or [] if _kind(f) == "poly_ref"
    }
    pairs: list[dict[str, str]] = []
    for name, kind in kinds.items():
        if not name.endswith("_type") or kind not in ("enum", "str", "text"):
            continue
        base = name[: -len("_type")]
        if base in poly_names:
            continue
        id_name = f"{base}_id"
        if id_name in names and kinds.get(id_name) in ("uuid", "str", "text"):
            pairs.append({"type_field": name, "id_field": id_name, "base": base})
    return pairs


def _finding(
    kind: str,
    severity: str,
    entity: str,
    fields: list[str],
    pattern_id: str,
    message: str,
    fix: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "kind": kind,
        "severity": severity,
        "entity": entity,
        "fields": fields,
        "pattern_id": pattern_id,
        "message": message,
        "fix": fix,
    }
    row.update(extra)
    return row


def _findings_for_entity(entity: Any) -> list[dict[str, Any]]:
    ename = str(entity.name)
    out: list[dict[str, Any]] = []
    exclusive_sets = _exclusive_sets_from_invariants(entity)
    for fields in exclusive_sets:
        out.append(
            _finding(
                "exclusive_fk_set",
                "info",
                ename,
                fields,
                str(PatternId.EXCLUSIVE_FKS),
                f"{ename} declares exclusive-anchor invariant on {', '.join(fields)}",
                "ensure list open: first_non_null(...) covers these fields",
            )
        )
    for pair in _hand_rolled_poly_pairs(entity):
        out.append(
            _finding(
                "hand_rolled_poly",
                "error",
                ename,
                [pair["type_field"], pair["id_field"]],
                str(PatternId.POLY_REF),
                f"{ename} has hand-rolled {pair['type_field']}+{pair['id_field']} "
                f"— use poly_ref {pair['base']} […]",
                "knowledge counter_prior id=polymorphic_associations",
            )
        )
    if getattr(entity, "subtype_of", None):
        out.append(
            _finding(
                "subtype_of",
                "info",
                ename,
                [],
                str(PatternId.TPT_SUBTYPE),
                f"{ename} subtype_of: {entity.subtype_of}",
            )
        )
    for f in getattr(entity, "fields", None) or []:
        if _kind(f) == "json":
            out.append(
                _finding(
                    "json_field",
                    "info",
                    ename,
                    [str(f.name)],
                    str(PatternId.JSON_EXTENSION),
                    f"{ename}.{f.name} is json — keep identity/FKs as columns",
                    "docs: data-representation JSONB hatch",
                )
            )
        if _kind(f) == "poly_ref":
            targets = getattr(getattr(f, "type", None), "poly_targets", None) or []
            out.append(
                _finding(
                    "poly_ref",
                    "info",
                    ename,
                    [str(f.name)],
                    str(PatternId.POLY_REF),
                    f"{ename}.{f.name} poly_ref targets={list(targets)}",
                    "dazzle db explain-scope for scope rules",
                )
            )
    opt_refs = _optional_ref_fields(entity)
    if len(opt_refs) >= 2 and not exclusive_sets:
        out.append(
            _finding(
                "multi_optional_refs_no_invariant",
                "warning",
                ename,
                opt_refs,
                str(PatternId.EXCLUSIVE_FKS),
                f"{ename} has {len(opt_refs)} optional refs without at-least-one-anchor invariant",
                "if exclusive parents: invariant: "
                + " or ".join(f"{n} != null" for n in opt_refs[:4]),
            )
        )
    return out


def _open_via_field_sets(appspec: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for surf in getattr(appspec, "surfaces", None) or []:
        targets = list(getattr(surf, "open_via_targets", None) or [])
        if len(targets) < 2:
            continue
        fields = [str(getattr(t, "via", "") or "") for t in targets if getattr(t, "via", None)]
        rows.append(
            {
                "surface": str(getattr(surf, "name", "")),
                "entity": str(getattr(surf, "entity_ref", "") or ""),
                "via_fields": fields,
            }
        )
    return rows


def _findings_for_open_via(appspec: Any, ent_by_name: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for hop in _open_via_field_sets(appspec):
        ent_name = hop["entity"]
        via = hop["via_fields"]
        entity = ent_by_name.get(ent_name)
        exclusive_fields: list[str] = []
        if entity is not None:
            for s in _exclusive_sets_from_invariants(entity):
                exclusive_fields.extend(s)
        missing_inv = not exclusive_fields or not set(via).issubset(set(exclusive_fields))
        out.append(
            _finding(
                "exclusive_fk_missing_invariant" if missing_inv else "open_via_multi_hop_ok",
                "warning" if missing_inv else "info",
                ent_name,
                via,
                str(PatternId.EXCLUSIVE_FKS),
                f"surface {hop['surface']}: open multi-hop via {via}"
                + (
                    " but entity lacks matching exclusive-anchor invariant"
                    if missing_inv
                    else " with matching exclusive-anchor invariant"
                ),
                "add invariant covering open-via fields" if missing_inv else None,
                surface=hop["surface"],
            )
        )
    return out


def _findings_missing_open(
    entities: list[Any], multi_open_entities: set[str]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entity in entities:
        ename = str(entity.name)
        sets = _exclusive_sets_from_invariants(entity)
        if sets and ename not in multi_open_entities:
            out.append(
                _finding(
                    "exclusive_fk_missing_open",
                    "warning",
                    ename,
                    sets[0],
                    str(PatternId.EXCLUSIVE_FKS),
                    f"{ename} has exclusive-anchor invariant but no list "
                    f"open: first_non_null(...) multi-hop found",
                    f"open: first_non_null({', '.join(sets[0])})",
                )
            )
    return out


def _entity_list(appspec: Any) -> list[Any]:
    domain = getattr(appspec, "domain", None)
    return list(
        getattr(appspec, "entities", None)
        or (getattr(domain, "entities", None) if domain is not None else None)
        or []
    )


def classify_appspec(appspec: Any) -> dict[str, Any]:
    """Walk entities + surfaces; return findings + summary counts."""
    entities = _entity_list(appspec)
    ent_by_name = {str(e.name): e for e in entities}
    findings: list[dict[str, Any]] = []
    for entity in entities:
        findings.extend(_findings_for_entity(entity))
    findings.extend(_findings_for_open_via(appspec, ent_by_name))
    multi_open = {h["entity"] for h in _open_via_field_sets(appspec)}
    findings.extend(_findings_missing_open(entities, multi_open))

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1
    return {
        "ok": True,
        "view": "representation_classify",
        "entity_count": len(entities),
        "finding_count": len(findings),
        "error_count": sum(1 for f in findings if f["severity"] == "error"),
        "warning_count": sum(1 for f in findings if f["severity"] == "warning"),
        "counts": counts,
        "findings": findings,
        "note": (
            "Classification is static AppSpec evidence (#1617). "
            "Use dazzle prove representation to gate integrity."
        ),
    }


def classify_project(project_root: Path) -> dict[str, Any]:
    """Load project AppSpec and classify."""
    root = project_root.resolve()
    if not (root / "dazzle.toml").is_file():
        return {"ok": False, "error": f"no dazzle.toml under {root}"}
    try:
        appspec = load_project_appspec(root)
    except Exception as exc:
        return {"ok": False, "error": f"load_project_appspec failed: {exc}"}
    result = classify_appspec(appspec)
    result["project_root"] = str(root)
    return result
