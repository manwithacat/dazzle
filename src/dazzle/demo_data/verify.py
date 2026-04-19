"""Blueprint verifier — static analysis of a demo data blueprint (#821).

Checks the ``field_patterns`` declared in a
:class:`dazzle.core.ir.demo_blueprint.DemoDataBlueprint` against the
corresponding :class:`dazzle.core.ir.EntitySpec` field types from the
compiled AppSpec. Flags strategy/type mismatches, unknown field
references, invalid enum values, length-cap violations, and missing
foreign-key strategies on ref fields.

This is the principled replacement for the narrow heuristic guard in
:func:`dazzle.demo_data.blueprint_generator._strategy_value_obviously_wrong`
(which was the quick rescue for the common drift patterns). The guard
stays in place as a runtime safety net; the verifier is the static
pass that catches problems before data is ever generated.

Typical callers:

* ``dazzle demo verify`` — CLI one-shot, exits non-zero on errors.
* ``demo_generate_impl`` — hard-gates generation on errors.
* ``dazzle qa trial --fresh-db`` — soft-gates, logs drift but
  continues (some imperfect data is better than none).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dazzle.core.ir.demo_blueprint import FieldStrategy
from dazzle.core.ir.fields import FieldTypeKind

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec, EntitySpec, FieldSpec
    from dazzle.core.ir.demo_blueprint import (
        DemoDataBlueprint,
        EntityBlueprint,
        FieldPattern,
    )


# Which IR field types each generation strategy can legitimately fill.
# Empty tuple == no constraint (strategy works for any field kind).
STRATEGY_COMPATIBILITY: dict[FieldStrategy, tuple[FieldTypeKind, ...]] = {
    FieldStrategy.UUID_GENERATE: (FieldTypeKind.UUID,),
    FieldStrategy.STATIC_LIST: (),  # values are opaque; generator just emits them
    FieldStrategy.ENUM_WEIGHTED: (FieldTypeKind.ENUM,),
    FieldStrategy.PERSON_NAME: (FieldTypeKind.STR, FieldTypeKind.TEXT),
    FieldStrategy.COMPANY_NAME: (FieldTypeKind.STR, FieldTypeKind.TEXT),
    FieldStrategy.EMAIL_FROM_NAME: (FieldTypeKind.STR, FieldTypeKind.EMAIL),
    FieldStrategy.USERNAME_FROM_NAME: (FieldTypeKind.STR,),
    FieldStrategy.HASHED_PASSWORD_PLACEHOLDER: (FieldTypeKind.STR, FieldTypeKind.TEXT),
    FieldStrategy.FREE_TEXT_LOREM: (FieldTypeKind.STR, FieldTypeKind.TEXT),
    FieldStrategy.NUMERIC_RANGE: (FieldTypeKind.INT, FieldTypeKind.FLOAT, FieldTypeKind.DECIMAL),
    FieldStrategy.CURRENCY_AMOUNT: (FieldTypeKind.MONEY, FieldTypeKind.DECIMAL),
    FieldStrategy.DATE_RELATIVE: (FieldTypeKind.DATE, FieldTypeKind.DATETIME),
    FieldStrategy.BOOLEAN_WEIGHTED: (FieldTypeKind.BOOL,),
    FieldStrategy.FOREIGN_KEY: (FieldTypeKind.REF, FieldTypeKind.BELONGS_TO),
    FieldStrategy.COMPOSITE: (),  # delegates to sub-strategies
    FieldStrategy.CUSTOM_PROMPT: (),  # LLM-generated, opaque
}


@dataclass
class Violation:
    """A single blueprint/IR mismatch.

    ``severity`` is either ``"error"`` (generation will produce invalid
    rows that fail at insert time) or ``"warning"`` (risky but not
    guaranteed to fail).
    """

    severity: str
    entity: str
    field: str
    rule: str
    message: str


@dataclass
class VerifyReport:
    violations: list[Violation] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(v.severity == "error" for v in self.violations)

    def errors(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "error"]

    def warnings(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "warning"]


def verify_blueprint(blueprint: DemoDataBlueprint, appspec: AppSpec) -> VerifyReport:
    """Check ``blueprint`` against ``appspec`` and return violations.

    Errors are blocker-level problems (generator will emit data that
    fails at insert time). Warnings are softer: the generator will
    emit something that *might* work but is off-spec.
    """
    report = VerifyReport()
    entity_by_name = {e.name: e for e in appspec.domain.entities}

    for entity_bp in blueprint.entities:
        entity_spec = entity_by_name.get(entity_bp.name)
        if entity_spec is None:
            report.violations.append(
                Violation(
                    severity="error",
                    entity=entity_bp.name,
                    field="",
                    rule="unknown_entity",
                    message=(
                        f"Blueprint references entity {entity_bp.name!r} "
                        f"which is not declared in the AppSpec."
                    ),
                )
            )
            continue

        fields_by_name = {f.name: f for f in entity_spec.fields}

        for pattern in entity_bp.field_patterns:
            _check_pattern(report, entity_bp, pattern, fields_by_name)

        _check_required_fields_have_patterns(report, entity_bp, entity_spec)

    return report


def _check_pattern(
    report: VerifyReport,
    entity_bp: EntityBlueprint,
    pattern: FieldPattern,
    fields_by_name: dict[str, FieldSpec],
) -> None:
    field_spec = fields_by_name.get(pattern.field_name)
    if field_spec is None:
        report.violations.append(
            Violation(
                severity="error",
                entity=entity_bp.name,
                field=pattern.field_name,
                rule="unknown_field",
                message=(
                    f"Blueprint pattern targets field "
                    f"{pattern.field_name!r} which is not declared on "
                    f"entity {entity_bp.name}."
                ),
            )
        )
        return

    allowed = STRATEGY_COMPATIBILITY.get(pattern.strategy, ())
    kind = field_spec.type.kind if field_spec.type else None
    if allowed and kind is not None and kind not in allowed:
        allowed_str = ", ".join(k.value for k in allowed)
        report.violations.append(
            Violation(
                severity="error",
                entity=entity_bp.name,
                field=pattern.field_name,
                rule="strategy_type_mismatch",
                message=(
                    f"Strategy {pattern.strategy.value!r} is not valid "
                    f"for field type {kind.value!r}. Allowed kinds: {allowed_str}."
                ),
            )
        )

    if pattern.strategy == FieldStrategy.ENUM_WEIGHTED and kind == FieldTypeKind.ENUM:
        _check_enum_values(report, entity_bp, pattern, field_spec)

    if (
        pattern.strategy == FieldStrategy.FREE_TEXT_LOREM
        and kind == FieldTypeKind.STR
        and field_spec.type
        and field_spec.type.max_length
    ):
        _check_lorem_length(report, entity_bp, pattern, field_spec)


def _check_enum_values(
    report: VerifyReport,
    entity_bp: EntityBlueprint,
    pattern: FieldPattern,
    field_spec: FieldSpec,
) -> None:
    declared = set(field_spec.type.enum_values or []) if field_spec.type else set()
    blueprint_values = set(pattern.params.get("enum_values") or [])
    unknown = blueprint_values - declared
    if unknown:
        report.violations.append(
            Violation(
                severity="error",
                entity=entity_bp.name,
                field=pattern.field_name,
                rule="enum_value_not_in_entity",
                message=(
                    f"Blueprint emits enum values {sorted(unknown)} that "
                    f"are not declared on the entity. Allowed: {sorted(declared)}."
                ),
            )
        )
    if not blueprint_values and declared:
        report.violations.append(
            Violation(
                severity="warning",
                entity=entity_bp.name,
                field=pattern.field_name,
                rule="enum_values_missing",
                message=(
                    "enum_weighted strategy has no enum_values in params; "
                    "generator will fall back to random entity values."
                ),
            )
        )


def _check_lorem_length(
    report: VerifyReport,
    entity_bp: EntityBlueprint,
    pattern: FieldPattern,
    field_spec: FieldSpec,
) -> None:
    max_length = field_spec.type.max_length if field_spec.type else None
    if not max_length:
        return
    max_words = pattern.params.get("max_words", 10)
    # Sentence of N words averages ~6-8 chars per word including spaces.
    estimated_chars = max_words * 7
    if estimated_chars > max_length:
        report.violations.append(
            Violation(
                severity="warning",
                entity=entity_bp.name,
                field=pattern.field_name,
                rule="lorem_may_exceed_length_cap",
                message=(
                    f"free_text_lorem with max_words={max_words} can produce "
                    f"~{estimated_chars} chars, but field cap is "
                    f"{max_length}. Consider lowering max_words or switching "
                    f"to static_list."
                ),
            )
        )


def _check_required_fields_have_patterns(
    report: VerifyReport,
    entity_bp: EntityBlueprint,
    entity_spec: EntitySpec,
) -> None:
    """Flag required fields with no generation pattern.

    At seed time, a required field with no pattern becomes NULL, which
    fails the NOT NULL constraint. The heuristic guard can NULL a field
    on purpose (wrong-type values), but that's a rescue — verify wants
    to flag the root cause up-front.
    """
    covered = {p.field_name for p in entity_bp.field_patterns}
    for f in entity_spec.fields:
        if f.name in covered:
            continue
        if getattr(f, "pk", False):
            continue  # generator auto-fills PKs
        if getattr(f, "required", False):
            report.violations.append(
                Violation(
                    severity="warning",
                    entity=entity_bp.name,
                    field=f.name,
                    rule="required_field_not_covered",
                    message=(
                        f"Required field {f.name!r} has no blueprint "
                        f"pattern; generated rows will set it to NULL "
                        f"and fail the NOT NULL constraint at insert."
                    ),
                )
            )
