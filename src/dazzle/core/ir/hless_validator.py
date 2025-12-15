"""
HLESS Validator - Section 7 Semantic Rule Enforcement.

This module enforces the semantic validation rules defined in HLESS Section 7:

1. FACT streams must not contain imperatives or requests
2. INTENT streams must not imply success
3. DERIVATION streams must reference source streams
4. OBSERVATION streams must not assert correctness
5. Order-dependent invariants must match partition key
6. Records written to FACT streams must be true forever

These rules are ENFORCED, not advisory. Violations require architectural
revision, not workaround.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .hless import (
    HLESSMode,
    HLESSPragma,
    HLESSViolation,
    RecordKind,
    StreamSpec,
)


@dataclass
class ValidationResult:
    """Result of HLESS validation."""

    valid: bool
    violations: list[HLESSViolation] = field(default_factory=list)
    warnings: list[HLESSViolation] = field(default_factory=list)

    @property
    def errors(self) -> list[HLESSViolation]:
        """Get only error-level violations."""
        return [v for v in self.violations if v.severity == "error"]


class HLESSValidator:
    """
    Enforces HLESS semantic rules (Section 7).

    This validator acts as a semantic guard, ensuring that StreamSpecs
    comply with HLESS principles before any code generation or runtime
    execution.

    Usage:
        validator = HLESSValidator()
        result = validator.validate(stream_spec)
        if not result.valid:
            for violation in result.violations:
                print(f"[{violation.rule}] {violation.message}")
    """

    # Imperative words that suggest a command/request, not a fact
    IMPERATIVE_PREFIXES = [
        "Create",
        "Update",
        "Delete",
        "Place",
        "Submit",
        "Send",
        "Process",
        "Execute",
        "Perform",
        "Trigger",
        "Start",
        "Stop",
        "Cancel",
        "Modify",
        "Change",
        "Set",
        "Add",
        "Remove",
    ]

    # Past tense indicators that suggest completion (invalid for INTENT)
    COMPLETION_SUFFIXES = [
        "Created",
        "Updated",
        "Deleted",
        "Placed",
        "Completed",
        "Processed",
        "Executed",
        "Finished",
        "Done",
        "Succeeded",
        "Approved",
        "Confirmed",
        "Shipped",
        "Delivered",
        "Paid",
    ]

    # Words that assert truth/correctness (invalid for OBSERVATION invariants)
    TRUTH_ASSERTION_PATTERNS = [
        r"\bis correct\b",
        r"\bis accurate\b",
        r"\bis true\b",
        r"\bguarantees?\b",
        r"\bensures?\b",
        r"\bwill always\b",
        r"\bmust be\b",
        r"\bauthoritative\b",
    ]

    # Words that imply ordering dependency
    ORDER_DEPENDENCY_PATTERNS = [
        r"\bbefore\b",
        r"\bafter\b",
        r"\bprecedes?\b",
        r"\bfollows?\b",
        r"\bsequence\b",
        r"\border(?:ed|ing)?\b",
        r"\bfirst\b",
        r"\blast\b",
        r"\bprevious\b",
        r"\bnext\b",
    ]

    # Forbidden terminology in HLESS strict mode
    # These words are ambiguous and must be replaced with precise RecordKind terminology
    FORBIDDEN_TERMINOLOGY = {
        "event": (
            "Ambiguous. Use 'stream' with explicit RecordKind "
            "(INTENT, FACT, OBSERVATION, or DERIVATION)"
        ),
        "Event": (
            "Ambiguous. Use schema naming like 'OrderPlaced' (FACT) or "
            "'OrderPlacementRequested' (INTENT)"
        ),
        "events": ("Ambiguous. Use 'streams' or specify the RecordKind"),
        "Events": ("Ambiguous. Use explicit RecordKind in naming"),
    }

    def validate(
        self,
        stream: StreamSpec,
        hless_pragma: HLESSPragma | None = None,
    ) -> ValidationResult:
        """
        Validate a StreamSpec against all HLESS rules.

        Args:
            stream: The StreamSpec to validate
            hless_pragma: Optional HLESS pragma for mode-specific enforcement

        Returns:
            ValidationResult with any violations found
        """
        violations: list[HLESSViolation] = []

        # Rule 0: Forbidden terminology in strict mode
        if hless_pragma and hless_pragma.mode == HLESSMode.STRICT:
            violations.extend(self._validate_forbidden_terminology(stream))

        # Rule 1: FACT streams must not contain imperatives
        if stream.record_kind == RecordKind.FACT:
            violations.extend(self._validate_fact_stream(stream))

        # Rule 2: INTENT streams must not imply success
        if stream.record_kind == RecordKind.INTENT:
            violations.extend(self._validate_intent_stream(stream))

        # Rule 3: DERIVATION streams must reference sources
        if stream.record_kind == RecordKind.DERIVATION:
            violations.extend(self._validate_derivation_stream(stream))

        # Rule 4: OBSERVATION streams must not assert correctness
        if stream.record_kind == RecordKind.OBSERVATION:
            violations.extend(self._validate_observation_stream(stream))

        # Rule 5: Order-dependent invariants must match partition key
        violations.extend(self._validate_ordering_invariants(stream))

        # Rule 6: All streams - validate required fields
        violations.extend(self._validate_required_fields(stream))

        return ValidationResult(
            valid=len([v for v in violations if v.severity == "error"]) == 0,
            violations=violations,
        )

    def validate_cross_stream_references(
        self,
        stream: StreamSpec,
        all_streams: dict[str, StreamSpec],
    ) -> list[HLESSViolation]:
        """
        Validate cross-stream references (outcomes, lineage).

        This is called during link phase when all streams are known.

        Args:
            stream: The StreamSpec to validate
            all_streams: All StreamSpecs indexed by name

        Returns:
            List of violations found
        """
        violations: list[HLESSViolation] = []

        # Validate INTENT outcomes
        if stream.record_kind == RecordKind.INTENT and stream.expected_outcomes:
            violations.extend(self._validate_intent_outcomes(stream, all_streams))

        # Validate DERIVATION lineage
        if stream.record_kind == RecordKind.DERIVATION and stream.lineage:
            violations.extend(self._validate_derivation_lineage(stream, all_streams))

        return violations

    def _validate_forbidden_terminology(self, stream: StreamSpec) -> list[HLESSViolation]:
        """Rule 0: Forbidden terminology in strict HLESS mode.

        The word 'event' is ambiguous and banned in strict mode.
        Use explicit RecordKind terminology instead.
        """
        violations: list[HLESSViolation] = []

        # Check stream name
        for term, reason in self.FORBIDDEN_TERMINOLOGY.items():
            if term.lower() in stream.name.lower():
                violations.append(
                    HLESSViolation(
                        rule="FORBIDDEN_TERMINOLOGY",
                        message=(
                            f"Stream name '{stream.name}' contains forbidden term '{term}'. "
                            f"{reason}"
                        ),
                        suggestion=(
                            "Rename stream to use explicit RecordKind terminology. "
                            "For example:\n"
                            "  - INTENT: order_placement_requests\n"
                            "  - FACT: order_facts\n"
                            "  - OBSERVATION: sensor_readings\n"
                            "  - DERIVATION: daily_order_stats"
                        ),
                        stream_name=stream.name,
                        severity="error",
                    )
                )
                break  # One violation per stream name is enough

        # Check schema names
        for schema in stream.schemas:
            for term, reason in self.FORBIDDEN_TERMINOLOGY.items():
                if term in schema.name:  # Case-sensitive for schema names
                    violations.append(
                        HLESSViolation(
                            rule="FORBIDDEN_TERMINOLOGY",
                            message=(
                                f"Schema name '{schema.name}' contains forbidden term '{term}'. "
                                f"{reason}"
                            ),
                            suggestion=(
                                "Use precise naming that reflects the RecordKind:\n"
                                "  - INTENT: OrderPlacementRequested, PaymentInitiated\n"
                                "  - FACT: OrderPlaced, PaymentConfirmed\n"
                                "  - OBSERVATION: TemperatureReading, StockQuote\n"
                                "  - DERIVATION: DailyTotal, RunningAverage"
                            ),
                            stream_name=stream.name,
                            schema_name=schema.name,
                            severity="error",
                        )
                    )
                    break  # One violation per schema is enough

        return violations

    def _validate_fact_stream(self, stream: StreamSpec) -> list[HLESSViolation]:
        """Rule 1: FACT streams must not contain imperatives or requests."""
        violations: list[HLESSViolation] = []

        for schema in stream.schemas:
            # Check if name sounds like a command
            if self._name_implies_request(schema.name):
                violations.append(
                    HLESSViolation(
                        rule="FACT_NO_IMPERATIVES",
                        message=(
                            f"FACT schema '{schema.name}' appears to be a request/command. "
                            f"FACT records must describe permanent truth, not intent."
                        ),
                        suggestion=(
                            f"Consider: Was '{schema.name}' requested, or did it happen? "
                            f"If requested, use INTENT stream. "
                            f"If it happened, use past tense (e.g., '{schema.name}ed' or similar)."
                        ),
                        stream_name=stream.name,
                        schema_name=schema.name,
                        severity="error",
                    )
                )

        return violations

    def _validate_intent_stream(self, stream: StreamSpec) -> list[HLESSViolation]:
        """Rule 2: INTENT streams must not imply success."""
        violations: list[HLESSViolation] = []

        for schema in stream.schemas:
            # Check if name implies completion
            if self._name_implies_completion(schema.name):
                violations.append(
                    HLESSViolation(
                        rule="INTENT_NO_SUCCESS",
                        message=(
                            f"INTENT schema '{schema.name}' implies completion. "
                            f"INTENT records describe requests, not outcomes."
                        ),
                        suggestion=(
                            f"Rename to '{self._suggest_intent_name(schema.name)}' "
                            f"or move to a FACT stream."
                        ),
                        stream_name=stream.name,
                        schema_name=schema.name,
                        severity="error",
                    )
                )

        # INTENT streams must declare expected outcomes
        if not stream.expected_outcomes:
            violations.append(
                HLESSViolation(
                    rule="INTENT_REQUIRES_OUTCOMES",
                    message=(
                        f"INTENT stream '{stream.name}' must declare expected_outcomes. "
                        f"What FACT records result from this intent?"
                    ),
                    suggestion=(
                        "Add an 'outcomes' block defining success/failure FACT emissions. "
                        "Example:\n"
                        "  outcomes:\n"
                        "    success:\n"
                        "      emits: [OrderPlaced]\n"
                        "    failure:\n"
                        "      emits: [OrderPlacementRejected]"
                    ),
                    stream_name=stream.name,
                    severity="error",
                )
            )

        return violations

    def _validate_derivation_stream(self, stream: StreamSpec) -> list[HLESSViolation]:
        """Rule 3: DERIVATION streams must reference source streams."""
        violations: list[HLESSViolation] = []

        if not stream.lineage:
            violations.append(
                HLESSViolation(
                    rule="DERIVATION_REQUIRES_LINEAGE",
                    message=(
                        f"DERIVATION stream '{stream.name}' must declare its source streams. "
                        f"Without lineage, the derivation cannot be rebuilt."
                    ),
                    suggestion=(
                        "Add a 'derives_from' block with source_streams list. "
                        "Example:\n"
                        "  derives_from:\n"
                        "    streams: [order_facts]\n"
                        "    type: aggregate\n"
                        "    rebuild: full_replay"
                    ),
                    stream_name=stream.name,
                    severity="error",
                )
            )
        elif not stream.lineage.source_streams:
            violations.append(
                HLESSViolation(
                    rule="DERIVATION_EMPTY_SOURCES",
                    message=(
                        f"DERIVATION stream '{stream.name}' has empty source_streams. "
                        f"At least one source stream is required."
                    ),
                    suggestion="Add the streams this derivation is computed from.",
                    stream_name=stream.name,
                    severity="error",
                )
            )

        # DERIVATION must have t_process
        if stream.time_semantics and not stream.time_semantics.t_process_field:
            violations.append(
                HLESSViolation(
                    rule="DERIVATION_REQUIRES_T_PROCESS",
                    message=(
                        f"DERIVATION stream '{stream.name}' should declare t_process. "
                        f"This is when the computation was performed."
                    ),
                    suggestion="Add 't_process: calculated_at' (or similar field name).",
                    stream_name=stream.name,
                    severity="warning",
                )
            )

        return violations

    def _validate_observation_stream(self, stream: StreamSpec) -> list[HLESSViolation]:
        """Rule 4: OBSERVATION streams must not assert correctness."""
        violations: list[HLESSViolation] = []

        for invariant in stream.invariants:
            if self._invariant_asserts_truth(invariant):
                violations.append(
                    HLESSViolation(
                        rule="OBSERVATION_NO_TRUTH_CLAIMS",
                        message=(
                            f"OBSERVATION invariant asserts correctness: '{invariant}'. "
                            f"OBSERVATION truth is 'this was observed', not 'this is correct'."
                        ),
                        suggestion=(
                            "Rephrase to describe observation properties, not truth claims. "
                            "Example: 'May contain duplicates' or 'Arrival may be out of order'."
                        ),
                        stream_name=stream.name,
                        severity="error",
                    )
                )

        return violations

    def _validate_ordering_invariants(self, stream: StreamSpec) -> list[HLESSViolation]:
        """Rule 5: Order-dependent invariants must match partition key."""
        violations: list[HLESSViolation] = []

        for invariant in stream.invariants:
            if self._invariant_requires_order(invariant):
                # Check if the invariant is scoped to the partition key
                if not self._invariant_mentions_partition_scope(
                    invariant, stream.partition_key, stream.ordering_scope
                ):
                    violations.append(
                        HLESSViolation(
                            rule="ORDER_SCOPE_MISMATCH",
                            message=(
                                f"Invariant '{invariant}' relies on ordering but doesn't "
                                f"reference the partition scope. Ordering is only guaranteed "
                                f"within partition_key '{stream.partition_key}'."
                            ),
                            suggestion=(
                                f"Either:\n"
                                f"1. Clarify the invariant applies within '{stream.ordering_scope}'\n"
                                f"2. Remove the ordering assumption\n"
                                f"3. Change the partition_key if global ordering is needed"
                            ),
                            stream_name=stream.name,
                            severity="warning",
                        )
                    )

        return violations

    def _validate_required_fields(self, stream: StreamSpec) -> list[HLESSViolation]:
        """Rule 6: Validate required fields for all streams."""
        violations: list[HLESSViolation] = []

        # Must have at least one schema
        if not stream.schemas:
            violations.append(
                HLESSViolation(
                    rule="STREAM_REQUIRES_SCHEMA",
                    message=f"Stream '{stream.name}' has no schemas defined.",
                    suggestion="Add at least one schema block to define record structure.",
                    stream_name=stream.name,
                    severity="error",
                )
            )

        # Must have time_semantics
        if not stream.time_semantics:
            violations.append(
                HLESSViolation(
                    rule="STREAM_REQUIRES_TIME_SEMANTICS",
                    message=f"Stream '{stream.name}' has no time_semantics.",
                    suggestion=(
                        "Add time_semantics with at least t_event_field. "
                        "Example: t_event: created_at"
                    ),
                    stream_name=stream.name,
                    severity="error",
                )
            )

        # Must have idempotency
        if not stream.idempotency:
            violations.append(
                HLESSViolation(
                    rule="STREAM_REQUIRES_IDEMPOTENCY",
                    message=f"Stream '{stream.name}' has no idempotency strategy.",
                    suggestion=(
                        "Add idempotency block. "
                        "Example:\n"
                        "  idempotency:\n"
                        "    type: deterministic_id\n"
                        "    field: record_id"
                    ),
                    stream_name=stream.name,
                    severity="error",
                )
            )

        return violations

    def _validate_intent_outcomes(
        self,
        stream: StreamSpec,
        all_streams: dict[str, StreamSpec],
    ) -> list[HLESSViolation]:
        """Validate INTENT stream outcomes reference valid FACT streams."""
        violations: list[HLESSViolation] = []

        if not stream.expected_outcomes:
            return violations

        for outcome in stream.expected_outcomes:
            target_stream_name = outcome.target_stream
            if not target_stream_name:
                # Need to infer target stream - this is a validation gap
                continue

            target_stream = all_streams.get(target_stream_name)

            if not target_stream:
                violations.append(
                    HLESSViolation(
                        rule="INTENT_OUTCOME_STREAM_NOT_FOUND",
                        message=(
                            f"INTENT outcome references stream '{target_stream_name}' "
                            f"which does not exist."
                        ),
                        suggestion=f"Create stream '{target_stream_name}' or fix the reference.",
                        stream_name=stream.name,
                        severity="error",
                    )
                )
                continue

            # Target must be a FACT stream
            if target_stream.record_kind != RecordKind.FACT:
                violations.append(
                    HLESSViolation(
                        rule="INTENT_OUTCOME_NOT_FACT",
                        message=(
                            f"INTENT outcome targets '{target_stream_name}' which is a "
                            f"{target_stream.record_kind.value} stream. "
                            f"INTENT outcomes must emit to FACT streams."
                        ),
                        suggestion="Change target to a FACT stream.",
                        stream_name=stream.name,
                        severity="error",
                    )
                )

            # Validate emitted schemas exist in target
            for schema_name in outcome.emits:
                if schema_name not in target_stream.schema_names():
                    violations.append(
                        HLESSViolation(
                            rule="INTENT_OUTCOME_SCHEMA_NOT_FOUND",
                            message=(
                                f"INTENT outcome emits '{schema_name}' but schema not found "
                                f"in target stream '{target_stream_name}'."
                            ),
                            suggestion=f"Add schema '{schema_name}' to stream '{target_stream_name}'.",
                            stream_name=stream.name,
                            severity="error",
                        )
                    )

            # Validate partition key compatibility
            if not stream.cross_partition and target_stream.partition_key != stream.partition_key:
                violations.append(
                    HLESSViolation(
                        rule="INTENT_OUTCOME_PARTITION_MISMATCH",
                        message=(
                            f"INTENT stream '{stream.name}' has partition_key '{stream.partition_key}' "
                            f"but outcome target '{target_stream_name}' has "
                            f"partition_key '{target_stream.partition_key}'. "
                            f"This may cause ordering issues."
                        ),
                        suggestion=(
                            "Either align partition keys or declare 'cross_partition: true' "
                            "if cross-partition writes are intentional."
                        ),
                        stream_name=stream.name,
                        severity="error",
                    )
                )

        return violations

    def _validate_derivation_lineage(
        self,
        stream: StreamSpec,
        all_streams: dict[str, StreamSpec],
    ) -> list[HLESSViolation]:
        """Validate DERIVATION lineage references valid source streams."""
        violations: list[HLESSViolation] = []

        if not stream.lineage:
            return violations

        for source_name in stream.lineage.source_streams:
            if source_name not in all_streams:
                violations.append(
                    HLESSViolation(
                        rule="DERIVATION_SOURCE_NOT_FOUND",
                        message=(
                            f"DERIVATION lineage references stream '{source_name}' "
                            f"which does not exist."
                        ),
                        suggestion=f"Create stream '{source_name}' or fix the reference.",
                        stream_name=stream.name,
                        severity="error",
                    )
                )

        return violations

    def _name_implies_request(self, name: str) -> bool:
        """Check if name sounds like a command/request."""
        return any(name.startswith(prefix) for prefix in self.IMPERATIVE_PREFIXES)

    def _name_implies_completion(self, name: str) -> bool:
        """Check if name implies something already happened."""
        return any(name.endswith(suffix) for suffix in self.COMPLETION_SUFFIXES)

    def _suggest_intent_name(self, name: str) -> str:
        """Suggest an INTENT-appropriate name for a completion-sounding name."""
        for suffix in self.COMPLETION_SUFFIXES:
            if name.endswith(suffix):
                base = name[: -len(suffix)]
                return f"{base}Requested"
        return f"{name}Requested"

    def _invariant_asserts_truth(self, invariant: str) -> bool:
        """Check if invariant makes truth claims inappropriate for OBSERVATION."""
        invariant_lower = invariant.lower()
        return any(re.search(pattern, invariant_lower) for pattern in self.TRUTH_ASSERTION_PATTERNS)

    def _invariant_requires_order(self, invariant: str) -> bool:
        """Check if invariant implies ordering dependency."""
        invariant_lower = invariant.lower()
        return any(
            re.search(pattern, invariant_lower) for pattern in self.ORDER_DEPENDENCY_PATTERNS
        )

    def _invariant_mentions_partition_scope(
        self,
        invariant: str,
        partition_key: str,
        ordering_scope: str,
    ) -> bool:
        """Check if invariant references the partition scope."""
        invariant_lower = invariant.lower()
        return (
            partition_key.lower() in invariant_lower
            or ordering_scope.lower().replace("_", " ") in invariant_lower
            or ordering_scope.lower() in invariant_lower
            or "within" in invariant_lower
            or "per " in invariant_lower
        )


def validate_stream(
    stream: StreamSpec,
    hless_pragma: HLESSPragma | None = None,
) -> ValidationResult:
    """
    Convenience function to validate a single StreamSpec.

    Args:
        stream: The StreamSpec to validate
        hless_pragma: Optional HLESS pragma for mode-specific enforcement

    Returns:
        ValidationResult with any violations found
    """
    validator = HLESSValidator()
    return validator.validate(stream, hless_pragma)


def validate_streams_with_cross_references(
    streams: list[StreamSpec],
    hless_pragma: HLESSPragma | None = None,
) -> ValidationResult:
    """
    Validate multiple StreamSpecs including cross-stream references.

    Args:
        streams: List of StreamSpecs to validate
        hless_pragma: Optional HLESS pragma for mode-specific enforcement

    Returns:
        Combined ValidationResult
    """
    validator = HLESSValidator()
    all_violations: list[HLESSViolation] = []

    # Index streams by name
    stream_index = {s.name: s for s in streams}

    # Validate each stream individually
    for stream in streams:
        result = validator.validate(stream, hless_pragma)
        all_violations.extend(result.violations)

    # Validate cross-stream references
    for stream in streams:
        cross_violations = validator.validate_cross_stream_references(stream, stream_index)
        all_violations.extend(cross_violations)

    return ValidationResult(
        valid=len([v for v in all_violations if v.severity == "error"]) == 0,
        violations=all_violations,
    )
