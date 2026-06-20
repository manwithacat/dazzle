"""Tests for the `scope: create:` payload-time SQL probe (#1311, ADR-0028).

Covers the two predicate shapes whose authorization boundary needs a DB
roundtrip at create time — FK-path (depth > 1) PathCheck and junction-table
ExistsCheck — plus the compiler probe builders that emit their SQL.

The walker (`scope_create_eval`) is DB-agnostic: it resolves the compiler's
`PayloadFieldRef` / `CurrentUserRef` / `UserAttrRef` markers to concrete
values and hands plain SQL + scalar params to an injected `probe` callable.
These tests inject a recording fake probe, so no database is required — they
assert the exact SQL/params handed to the probe and the allow/deny outcome.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("fastapi")  # predicate_compiler imports the back-runtime stack

from dazzle.core.ir.fk_graph import FKEdge, FKGraph
from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    ExistsBinding,
    ExistsCheck,
    PathCheck,
    ValueRef,
)
from dazzle.http.runtime.predicate_compiler import (
    CurrentUserRef,
    PayloadFieldRef,
    UserAttrRef,
    compile_exists_check_probe,
    compile_path_check_probe,
)
from dazzle.http.runtime.scope_create_eval import (
    ScopeCreateUnsupportedError,
    check_create_predicate,
)


def _graph() -> FKGraph:
    """ClassEnrolment -teaching_group_id-> TeachingGroup(department);
    Task -team_id-> Team(name); TeamMembership(user, team) junction;
    Feedback -manuscript_id-> Manuscript -assessment_event_id-> AssessmentEvent(school_id)
    (a 2-hop chain for the depth-3 nesting test)."""
    g = FKGraph()
    g._edges = {
        "ClassEnrolment": [FKEdge("ClassEnrolment", "teaching_group_id", "TeachingGroup")],
        "Task": [FKEdge("Task", "team_id", "Team")],
        "Feedback": [FKEdge("Feedback", "manuscript_id", "Manuscript")],
        "Manuscript": [FKEdge("Manuscript", "assessment_event_id", "AssessmentEvent")],
    }
    g._fields = {
        "ClassEnrolment": {"id", "teaching_group_id"},
        "TeachingGroup": {"id", "department"},
        "Task": {"id", "team_id"},
        "Team": {"id", "name"},
        "TeamMembership": {"id", "user", "team"},
        "Feedback": {"id", "manuscript_id"},
        "Manuscript": {"id", "assessment_event_id"},
        "AssessmentEvent": {"id", "school_id"},
    }
    return g


class _FakeProbe:
    """Records (sql, params) and returns a preset boolean."""

    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls: list[tuple[str, list[Any]]] = []

    def __call__(self, sql: str, params: list[Any]) -> bool:
        self.calls.append((sql, params))
        return self.result


# ---------------------------------------------------------------------------
# Compiler probe builders — SQL shape
# ---------------------------------------------------------------------------


def test_path_check_probe_sql_shape() -> None:
    """A depth-2 PathCheck compiles to an EXISTS probe binding the payload FK
    as `"id" = %s` (uuid column on the left — coercion-safe) and the terminal
    condition after it. params[0] is the root-FK PayloadFieldRef."""
    pred = PathCheck(
        path=["teaching_group", "department"],
        op=CompOp.EQ,
        value=ValueRef(user_attr="department"),
    )
    sql, params = compile_path_check_probe(pred, "ClassEnrolment", _graph())
    assert sql == 'EXISTS (SELECT 1 FROM "TeachingGroup" WHERE "id" = %s AND ("department" = %s))'
    assert params == [PayloadFieldRef("teaching_group_id"), UserAttrRef("department")]


def test_path_check_probe_depth_three_nests() -> None:
    """A depth-3 (2-hop) path nests an inner ``IN (SELECT …)`` inside the
    EXISTS body; the root FK is still bound as ``"id" = %s``."""
    pred = PathCheck(
        path=["manuscript", "assessment_event", "school_id"],
        op=CompOp.EQ,
        value=ValueRef(user_attr="school"),
    )
    sql, params = compile_path_check_probe(pred, "Feedback", _graph())
    assert sql == (
        'EXISTS (SELECT 1 FROM "Manuscript" WHERE "id" = %s AND '
        '("assessment_event_id" IN (SELECT "id" FROM "AssessmentEvent" '
        'WHERE "school_id" = %s)))'
    )
    assert params == [PayloadFieldRef("manuscript_id"), UserAttrRef("school")]


def test_exists_check_probe_binds_entity_column_to_payload() -> None:
    """An ExistsCheck probe binds `current_user` to a CurrentUserRef and the
    entity-side column to a PayloadFieldRef (the root row doesn't exist yet)."""
    pred = ExistsCheck(
        target_entity="TeamMembership",
        bindings=[
            ExistsBinding(junction_field="user", target="current_user"),
            ExistsBinding(junction_field="team", target="team"),
        ],
    )
    sql, params = compile_exists_check_probe(pred, "Task", _graph())
    assert sql == 'EXISTS (SELECT 1 FROM "TeamMembership" WHERE "user" = %s AND "team" = %s)'
    assert params == [CurrentUserRef(), PayloadFieldRef("team")]


def test_not_exists_check_probe_emits_not_exists() -> None:
    pred = ExistsCheck(
        target_entity="BlockList",
        bindings=[ExistsBinding(junction_field="user", target="current_user")],
        negated=True,
    )
    sql, _ = compile_exists_check_probe(pred, "Task", _graph())
    assert sql.startswith("NOT EXISTS (")


# ---------------------------------------------------------------------------
# Walker — marker resolution + allow/deny via the injected probe
# ---------------------------------------------------------------------------


def _tg_predicate() -> PathCheck:
    return PathCheck(
        path=["teaching_group", "department"],
        op=CompOp.EQ,
        value=ValueRef(user_attr="department"),
    )


def test_fk_path_resolves_markers_and_allows_when_probe_matches() -> None:
    probe = _FakeProbe(result=True)
    allowed = check_create_predicate(
        _tg_predicate(),
        {"teaching_group_id": "tg-1", "title": "Algebra"},
        user_id="u-1",
        user_attrs={"department": "math"},
        probe=probe,
        fk_graph=_graph(),
        entity_name="ClassEnrolment",
    )
    assert allowed is True
    # The probe saw concrete values, not markers: payload FK then user attr.
    sql, params = probe.calls[0]
    assert sql == 'EXISTS (SELECT 1 FROM "TeachingGroup" WHERE "id" = %s AND ("department" = %s))'
    assert params == ["tg-1", "math"]


def test_fk_path_denies_when_probe_misses() -> None:
    probe = _FakeProbe(result=False)
    allowed = check_create_predicate(
        _tg_predicate(),
        {"teaching_group_id": "tg-foreign"},
        user_id="u-1",
        user_attrs={"department": "math"},
        probe=probe,
        fk_graph=_graph(),
        entity_name="ClassEnrolment",
    )
    assert allowed is False


def test_fk_path_resolves_payload_relation_name_variant() -> None:
    """Payload keyed under the relation name (`teaching_group`) still resolves
    even though the compiler asks for the FK column (`teaching_group_id`)."""
    probe = _FakeProbe(result=True)
    check_create_predicate(
        _tg_predicate(),
        {"teaching_group": "tg-1"},
        user_id="u-1",
        user_attrs={"department": "math"},
        probe=probe,
        fk_graph=_graph(),
        entity_name="ClassEnrolment",
    )
    _, params = probe.calls[0]
    assert params == ["tg-1", "math"]


def test_fk_path_missing_payload_fk_passes_none_to_probe() -> None:
    """A missing root FK resolves to None (→ NULL IN (…) → no row → deny).
    The walker hands None to the probe; the DB would return no row."""
    probe = _FakeProbe(result=False)
    allowed = check_create_predicate(
        _tg_predicate(),
        {"title": "no FK here"},
        user_id="u-1",
        user_attrs={"department": "math"},
        probe=probe,
        fk_graph=_graph(),
        entity_name="ClassEnrolment",
    )
    assert allowed is False
    _, params = probe.calls[0]
    assert params == [None, "math"]


def test_exists_check_resolves_current_user_and_payload() -> None:
    pred = ExistsCheck(
        target_entity="TeamMembership",
        bindings=[
            ExistsBinding(junction_field="user", target="current_user"),
            ExistsBinding(junction_field="team", target="team"),
        ],
    )
    probe = _FakeProbe(result=True)
    allowed = check_create_predicate(
        pred,
        {"team": "team-7"},
        user_id="u-42",
        probe=probe,
        fk_graph=_graph(),
        entity_name="Task",
    )
    assert allowed is True
    sql, params = probe.calls[0]
    assert sql == 'EXISTS (SELECT 1 FROM "TeamMembership" WHERE "user" = %s AND "team" = %s)'
    assert params == ["u-42", "team-7"]


def test_exists_check_current_user_prefers_entity_id() -> None:
    """`current_user` in a probe leaf resolves to the DSL User-entity id
    (`entity_id`) when available — consistent with the read/list scope path —
    not the auth UserRecord id. A junction FK holds the entity id."""
    pred = ExistsCheck(
        target_entity="TeamMembership",
        bindings=[ExistsBinding(junction_field="user", target="current_user")],
    )
    probe = _FakeProbe(result=True)
    check_create_predicate(
        pred,
        {},
        user_id="auth-1",
        user_attrs={"entity_id": "domain-user-7"},
        probe=probe,
        fk_graph=_graph(),
        entity_name="Task",
    )
    _, params = probe.calls[0]
    assert params == ["domain-user-7"]  # entity_id, not "auth-1"


def test_exists_check_current_user_falls_back_to_user_id() -> None:
    """When entity_id is unresolvable, `current_user` falls back to the auth
    user id (the common case where auth id == entity id by convention)."""
    pred = ExistsCheck(
        target_entity="TeamMembership",
        bindings=[ExistsBinding(junction_field="user", target="current_user")],
    )
    probe = _FakeProbe(result=True)
    check_create_predicate(
        pred,
        {},
        user_id="auth-1",
        user_attrs={},  # no entity_id
        probe=probe,
        fk_graph=_graph(),
        entity_name="Task",
    )
    _, params = probe.calls[0]
    assert params == ["auth-1"]


def test_bool_composite_mixes_python_leaf_and_probe_leaf() -> None:
    """`status = "active" AND teaching_group.department = current_user.department`
    — the ColumnCheck evaluates in Python (no probe), the PathCheck via probe.
    The AND only probes when the Python leaf already passed."""
    pred = BoolComposite.make(
        BoolOp.AND,
        [
            ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active")),
            _tg_predicate(),
        ],
    )
    probe = _FakeProbe(result=True)
    allowed = check_create_predicate(
        pred,
        {"status": "active", "teaching_group_id": "tg-1"},
        user_id="u-1",
        user_attrs={"department": "math"},
        probe=probe,
        fk_graph=_graph(),
        entity_name="ClassEnrolment",
    )
    assert allowed is True
    assert len(probe.calls) == 1  # probe fired once (for the FK-path leaf)


def test_bool_composite_python_leaf_fails_short_circuits_probe() -> None:
    """When the Python leaf of an AND fails, the probe is never called
    (short-circuit) — and the whole predicate denies."""
    pred = BoolComposite.make(
        BoolOp.AND,
        [
            ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active")),
            _tg_predicate(),
        ],
    )
    probe = _FakeProbe(result=True)
    allowed = check_create_predicate(
        pred,
        {"status": "archived", "teaching_group_id": "tg-1"},
        user_id="u-1",
        user_attrs={"department": "math"},
        probe=probe,
        fk_graph=_graph(),
        entity_name="ClassEnrolment",
    )
    assert allowed is False
    assert probe.calls == []  # short-circuited before the probe


def test_probe_required_but_missing_raises_backstop() -> None:
    """No probe + an FK-path leaf → ScopeCreateUnsupportedError (the
    enforcer maps this to default-deny)."""
    with pytest.raises(ScopeCreateUnsupportedError, match="depth > 1"):
        check_create_predicate(
            _tg_predicate(),
            {"teaching_group_id": "tg-1"},
            user_id="u-1",
            user_attrs={"department": "math"},
            fk_graph=_graph(),
            entity_name="ClassEnrolment",
        )
