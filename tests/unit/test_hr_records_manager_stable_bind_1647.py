"""Cycle 1647 Goal B: manager Person seed binds to STABLE_PERSONA_USER_IDS.

Without this, manager My Team / Reporting desks empty under current_user
scope (no User entity — bare current_user must equal Person.id).
"""

from __future__ import annotations

import json
from pathlib import Path

from dazzle.product_quality.persona_homes import STABLE_PERSONA_USER_IDS

REPO = Path(__file__).resolve().parents[2]
SEED = REPO / "examples" / "hr_records" / "dsl" / "seeds" / "demo_data" / "Person.jsonl"
LINKS = REPO / "examples" / "hr_records" / "dsl" / "seeds" / "demo_data" / "ManagerLink.jsonl"


def _people() -> list[dict]:
    return [json.loads(line) for line in SEED.read_text().splitlines() if line.strip()]


def _links() -> list[dict]:
    return [json.loads(line) for line in LINKS.read_text().splitlines() if line.strip()]


def test_manager_person_at_stable_id_and_demo_email() -> None:
    mid = STABLE_PERSONA_USER_IDS["manager"]
    people = {p["id"]: p for p in _people()}
    assert mid in people, "manager Person must use STABLE manager UUID"
    row = people[mid]
    assert row["email"] == "manager@demo.dazzle.local"
    assert "Griffin" in row["legal_name"] or row["preferred_name"] == "Geoff"


def test_manager_has_outbound_reporting_links() -> None:
    mid = STABLE_PERSONA_USER_IDS["manager"]
    outbound = [L for L in _links() if L["manager"] == mid and L.get("end_date") in (None, "")]
    assert len(outbound) >= 2, f"expected ≥2 active reports for manager, got {outbound}"


def test_employee_person_at_stable_id() -> None:
    eid = STABLE_PERSONA_USER_IDS["employee"]
    people = {p["id"]: p for p in _people()}
    assert eid in people
    assert people[eid]["email"] == "employee@demo.dazzle.local"
