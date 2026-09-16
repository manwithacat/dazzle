"""Validate `ingest:` declarations (#1676)."""

from __future__ import annotations

from dazzle.core import ir


def _unique_field_sets(entity: ir.EntitySpec) -> list[set[str]]:
    uniques: list[set[str]] = []
    for constraint in entity.constraints:
        if constraint.kind == ir.ConstraintKind.UNIQUE:
            uniques.append(set(constraint.fields))
    for field in entity.fields:
        if field.is_unique:
            uniques.append({field.name})
    return uniques


def _check_one_ingest(spec: ir.IngestSpec, entity: ir.EntitySpec, label: str) -> list[str]:
    errors: list[str] = []
    field_names = {f.name for f in entity.fields}
    for key in spec.key:
        if key not in field_names:
            errors.append(f"{label}: key field '{key}' is not on {spec.entity}")
    if spec.protect is not None and spec.protect.field not in field_names:
        errors.append(f"{label}: protect field '{spec.protect.field}' is not on {spec.entity}")
    key_set = set(spec.key)
    if key_set and key_set not in _unique_field_sets(entity):
        errors.append(
            f"{label}: key {sorted(key_set)} must match a unique constraint "
            f"on {spec.entity} (entity `unique a, b` or field `unique`)"
        )
    return errors


def validate_ingests(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    entities = {e.name: e for e in appspec.domain.entities}
    seen: set[str] = set()

    for spec in appspec.ingests:
        label = f"ingest {spec.name}"
        if spec.name in seen:
            errors.append(f"{label}: duplicate ingest name")
        seen.add(spec.name)
        entity = entities.get(spec.entity)
        if entity is None:
            errors.append(f"{label}: unknown entity '{spec.entity}'")
            continue
        errors.extend(_check_one_ingest(spec, entity, label))

    return errors, warnings
