"""Reconciliation engine for UX contract failures.

Given a failed contract, its associated VerifiableTriple, and the HTML that
was actually rendered, the reconciler produces a ``Diagnosis`` that tells an
agent *what went wrong* and *which DSL levers* could fix it.

This is Layer C of the IR Triple Enrichment spec — the back-propagation
engine that makes ``/ux-converge`` smarter by surfacing actionable DSL
changes instead of opaque pass/fail results.

The reconciler is **pure** — no side effects, no network calls.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from dazzle.core.ir.domain import EntitySpec
    from dazzle.core.ir.surfaces import SurfaceSpec
    from dazzle.core.ir.triples import VerifiableTriple
    from dazzle.testing.ux.contracts import Contract


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class DiagnosisKind(StrEnum):
    WIDGET_MISMATCH = "widget_mismatch"
    ACTION_MISSING = "action_missing"
    ACTION_UNEXPECTED = "action_unexpected"
    FIELD_MISSING = "field_missing"
    PERMISSION_GAP = "permission_gap"
    SURFACE_MISSING = "surface_missing"
    TEMPLATE_BUG = "template_bug"


class DSLLever(BaseModel, frozen=True):
    """A single DSL change that could fix or mitigate the diagnosed issue.

    Note: ``construct`` shadows a deprecated ``BaseModel.construct()`` method.
    Pydantic emits a UserWarning; this is harmless and the field name matches
    the spec.
    """

    file: str = ""
    construct: str  # type: ignore[assignment]  # e.g. "entity.Task.access.permit"
    current_value: str
    suggested_value: str
    explanation: str


class Diagnosis(BaseModel, frozen=True):
    """Structured diagnosis of a single contract failure."""

    contract_id: str
    kind: DiagnosisKind
    triple: str  # "{entity}.{surface}.{persona}"
    observation: str
    expectation: str
    levers: list[DSLLever] = Field(default_factory=list)
    category: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ACTION_KEYWORDS = re.compile(r"\b(edit|delete|transition|update|remove)\b", re.IGNORECASE)
_FIELD_KEYWORDS = re.compile(r"\b(field|missing field|Missing)\b", re.IGNORECASE)


def _entity_from_contract(contract: Contract) -> str:
    """Extract entity name from any contract type."""
    return getattr(contract, "entity", "") or ""


def _triple_label(contract: Contract, triple: VerifiableTriple | None) -> str:
    """Build the ``{entity}.{surface}.{persona}`` label."""
    entity = _entity_from_contract(contract)
    if triple is not None:
        return f"{triple.entity}.{triple.surface}.{triple.persona}"
    persona = getattr(contract, "persona", "unknown")
    surface = getattr(contract, "surface", "unknown")
    return f"{entity}.{surface}.{persona}"


def _permit_lever(entity: str, operation: str = "") -> DSLLever:
    """Lever pointing at the entity's permit rules."""
    for_label = "" if not operation else f" for {operation}"
    return DSLLever(
        construct=f"entity.{entity}.access.permit",
        current_value="",
        suggested_value=f"permit {operation} rule" if operation else "permit rule",
        explanation=f"Add or update permit rule on entity {entity}{for_label}",
    )


def _access_lever(entity: str) -> DSLLever:
    """Lever pointing at the entity's access block (restrict/forbid)."""
    return DSLLever(
        construct=f"entity.{entity}.access",
        current_value="",
        suggested_value="restrict or add forbid rule",
        explanation=f"Restrict or add forbid rule on entity {entity} access block",
    )


def _field_lever(entity: str, surface: str) -> DSLLever:
    """Lever pointing at the surface's section elements."""
    return DSLLever(
        construct=f"surface.{surface}.section.elements",
        current_value="",
        suggested_value="add missing field element",
        explanation=f"Add missing field element to surface {surface} for entity {entity}",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reconcile(
    contract: Contract,
    triple: VerifiableTriple | None,
    html: str,
    appspec_entities: list[EntitySpec],
    appspec_surfaces: list[SurfaceSpec],
) -> Diagnosis:
    """Produce a structured diagnosis for a failed contract.

    Logic:
    1. If triple is None → PERMISSION_GAP
    2. If contract is RBACContract:
       - expected_present=True but not in HTML → ACTION_MISSING
       - expected_present=False but found in HTML → ACTION_UNEXPECTED
    3. If contract is DetailViewContract and error mentions action keywords → ACTION_MISSING
    4. If contract is CreateFormContract/EditFormContract and error mentions field → FIELD_MISSING
    5. Default fallback → TEMPLATE_BUG (no DSL levers)

    Args:
        contract: The failed contract.
        triple: The VerifiableTriple for this (entity, surface, persona) combo,
            or ``None`` if no triple could be derived.
        html: The raw HTML that was actually rendered.
        appspec_entities: All EntitySpec instances (for context).
        appspec_surfaces: All SurfaceSpec instances (for context).

    Returns:
        A ``Diagnosis`` with the appropriate kind and levers.
    """
    # Lazy imports to avoid circular dependencies at module level
    from dazzle.testing.ux.contracts import (
        CreateFormContract,
        DetailViewContract,
        EditFormContract,
        RBACContract,
    )

    entity = _entity_from_contract(contract)
    label = _triple_label(contract, triple)
    error = contract.error or ""

    # 1. No triple → PERMISSION_GAP
    if triple is None:
        operation = getattr(contract, "operation", "")
        return Diagnosis(
            contract_id=contract.contract_id,
            kind=DiagnosisKind.PERMISSION_GAP,
            triple=label,
            observation=f"No verifiable triple derived for {label}",
            expectation="A triple should exist for this entity/surface/persona combination",
            levers=[_permit_lever(entity, operation)],
        )

    # 2. RBACContract
    if isinstance(contract, RBACContract):
        operation = contract.operation
        if contract.expected_present and contract.status == "failed":
            return Diagnosis(
                contract_id=contract.contract_id,
                kind=DiagnosisKind.ACTION_MISSING,
                triple=label,
                observation=error or f"Expected {operation} action present but not found",
                expectation=f"{operation} action should be present for persona",
                levers=[_permit_lever(entity, operation)],
            )
        if not contract.expected_present and contract.status == "failed":
            return Diagnosis(
                contract_id=contract.contract_id,
                kind=DiagnosisKind.ACTION_UNEXPECTED,
                triple=label,
                observation=error or f"Found {operation} action but should not be present",
                expectation=f"{operation} action should NOT be present for persona",
                levers=[_access_lever(entity)],
            )

    # 3. DetailViewContract with action-related error
    if isinstance(contract, DetailViewContract) and _ACTION_KEYWORDS.search(error):
        return Diagnosis(
            contract_id=contract.contract_id,
            kind=DiagnosisKind.ACTION_MISSING,
            triple=label,
            observation=error,
            expectation="Expected action elements in detail view",
            levers=[_permit_lever(entity)],
        )

    # 4. CreateFormContract / EditFormContract with field-related error
    if isinstance(contract, (CreateFormContract, EditFormContract)) and _FIELD_KEYWORDS.search(
        error
    ):
        surface = getattr(contract, "surface", "") or getattr(triple, "surface", "")
        return Diagnosis(
            contract_id=contract.contract_id,
            kind=DiagnosisKind.FIELD_MISSING,
            triple=label,
            observation=error,
            expectation="All declared fields should be present in the form",
            levers=[_field_lever(entity, surface)],
        )

    # 5. Default fallback → TEMPLATE_BUG
    return Diagnosis(
        contract_id=contract.contract_id,
        kind=DiagnosisKind.TEMPLATE_BUG,
        triple=label,
        observation=error or "Contract failed but cause is not a DSL issue",
        expectation="HTML should match the contract expectations",
        levers=[],
    )
