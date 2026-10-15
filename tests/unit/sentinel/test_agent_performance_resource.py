"""Tests for the Performance & Resource detection agent (PR-01 to PR-03, PR-05, PR-07, PR-08).

One table: each case builds an AppSpec, runs one heuristic and pins the exact
findings (see ``assert_findings``). Agent identity, heuristic order and the
clean-spec run live in ``test_registry.py``.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from dazzle.core.ir import FieldTypeKind
from dazzle.core.ir.process import OverlapPolicy
from dazzle.core.ir.views import ViewFieldSpec, ViewSpec
from dazzle.sentinel.agents.performance_resource import PerformanceResourceAgent
from dazzle.sentinel.models import Severity

from .conftest import (
    assert_findings,
    make_appspec,
    make_entity,
    make_field,
    pk_field,
    ref_field,
    str_field,
)

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _surface(
    name: str, entity_ref: str | None, mode: str = "list", view_ref: str | None = None
) -> MagicMock:
    surface = MagicMock()
    surface.name = name
    surface.mode = mode
    surface.entity_ref = entity_ref
    surface.view_ref = view_ref
    if entity_ref is None:
        surface.entity = None
    return surface


def _has_many(name: str, target: str) -> Any:
    return make_field(name, FieldTypeKind.HAS_MANY, ref_entity=target)


def _three_has_many() -> list[Any]:
    return [
        _has_many("items", "OrderItem"),
        _has_many("payments", "Payment"),
        _has_many("notes", "Note"),
    ]


def _three_refs() -> list[Any]:
    return [
        ref_field("customer", "Customer"),
        ref_field("product", "Product"),
        ref_field("warehouse", "Warehouse"),
    ]


def _order_on(surface: MagicMock, *fields: Any) -> Any:
    return make_appspec([make_entity("Order", [pk_field(), *fields])], surfaces=[surface])


def _order_list(*fields: Any) -> Any:
    return _order_on(_surface("order_list", "Order"), *fields)


def _wide(name: str, n_str_fields: int, surface: MagicMock, views: list | None = None) -> Any:
    fields = [pk_field()] + [str_field(f"field_{i}") for i in range(n_str_fields)]
    return make_appspec([make_entity(name, fields)], surfaces=[surface], views=views)


def _indexed_ref() -> Any:
    entity = MagicMock()
    entity.name = "Order"
    entity.fields = [pk_field(), ref_field("customer", "Customer")]
    constraint = MagicMock()
    constraint.kind = "index"
    constraint.fields = ["customer"]
    entity.constraints = [constraint]
    return make_appspec([entity])


def _process(name: str = "approve_order", **attrs: Any) -> MagicMock:
    process = MagicMock()
    process.name = name
    for key, value in attrs.items():
        setattr(process, key, value)
    return process


def _one_process(**attrs: Any) -> Any:
    return make_appspec(processes=[_process(**attrs)])


def _surfaces(*specs: tuple[str, str, str]) -> Any:
    return make_appspec(surfaces=[_surface(n, e, m) for n, e, m in specs])


_CRUD = (
    ("task_list", "Task", "list"),
    ("task_detail", "Task", "view"),
    ("task_create", "Task", "create"),
    ("task_edit", "Task", "edit"),
)


def _pr(n: int, severity: Severity | None = None, **extra: Any) -> list[dict[str, Any]]:
    want: dict[str, Any] = {"heuristic_id": f"PR-0{n}", **extra}
    if severity is not None:
        want["severity"] = severity
    return [want]


# ---------------------------------------------------------------------------
# Heuristic table
# ---------------------------------------------------------------------------

CASES = [
    # PR-01  N+1 risk: list surface over an entity with >=3 has_many
    # (ref fields are auto-eager-loaded; has_many are not).
    pytest.param(
        "n_plus_1_list_surface",
        lambda: _order_list(*_three_refs()),
        [],
        id="PR-01-ref-only-entity-eager-loaded",
    ),
    pytest.param(
        "n_plus_1_list_surface",
        lambda: _order_list(*_three_has_many()),
        _pr(1, Severity.HIGH, title_has="order_list"),
        id="PR-01-flags-three-has-many",
    ),
    pytest.param(
        "n_plus_1_list_surface",
        lambda: _order_list(ref_field("customer", "Customer"), *_three_has_many()),
        _pr(1, Severity.HIGH),
        id="PR-01-only-has-many-counts-alongside-refs",
    ),
    pytest.param(
        "n_plus_1_list_surface",
        lambda: _order_list(
            ref_field("customer", "Customer"),
            _has_many("items", "OrderItem"),
            make_field("invoice", FieldTypeKind.HAS_ONE, ref_entity="Invoice"),
        ),
        [],
        id="PR-01-mixed-relations-below-threshold",
    ),
    pytest.param(
        "n_plus_1_list_surface",
        lambda: _order_list(*_three_refs()[:2]),
        [],
        id="PR-01-two-refs",
    ),
    pytest.param(
        "n_plus_1_list_surface",
        lambda: _order_on(_surface("order_detail", "Order", "detail"), *_three_has_many()),
        [],
        id="PR-01-non-list-surface",
    ),
    pytest.param(
        "n_plus_1_list_surface",
        lambda: make_appspec(surfaces=[_surface("dashboard", None)]),
        [],
        id="PR-01-surface-without-entity",
    ),
    pytest.param("n_plus_1_list_surface", make_appspec, [], id="PR-01-no-surfaces"),
    pytest.param(
        "n_plus_1_list_surface",
        lambda: make_appspec(surfaces=[_surface("order_list", "NonExistent")]),
        [],
        id="PR-01-entity-not-found",
    ),
    # PR-02  ref field without an index
    pytest.param(
        "ref_without_index",
        lambda: make_appspec(
            [make_entity("Order", [pk_field(), ref_field("customer", "Customer")])]
        ),
        _pr(2, Severity.MEDIUM, title_has="Order.customer"),
        id="PR-02-flags-ref-without-index",
    ),
    pytest.param("ref_without_index", _indexed_ref, [], id="PR-02-index-covers-field"),
    pytest.param(
        "ref_without_index",
        lambda: make_appspec([make_entity("Task", [pk_field(), str_field("title")])]),
        [],
        id="PR-02-ignores-non-ref",
    ),
    # PR-03  process with ALLOW overlap policy
    pytest.param(
        "process_allow_overlap",
        lambda: _one_process(overlap_policy=OverlapPolicy.ALLOW),
        _pr(3, Severity.MEDIUM, title_has="approve_order"),
        id="PR-03-flags-allow-overlap",
    ),
    *[
        pytest.param(
            "process_allow_overlap",
            lambda p=policy: _one_process(overlap_policy=p),
            [],
            id=f"PR-03-{policy.value}-is-safe",
        )
        for policy in (OverlapPolicy.SKIP, OverlapPolicy.QUEUE, OverlapPolicy.CANCEL_PREVIOUS)
    ],
    pytest.param("process_allow_overlap", make_appspec, [], id="PR-03-no-processes"),
    # PR-05  list surface over an entity with >=10 fields (title names both)
    pytest.param(
        "large_entity_list_surface",
        lambda: _wide("BigEntity", 10, _surface("big_list", "BigEntity")),
        _pr(5, Severity.MEDIUM, title_has=("big_list", "BigEntity")),
        id="PR-05-flags-eleven-fields",
    ),
    pytest.param(
        "large_entity_list_surface",
        lambda: _wide("TenFields", 9, _surface("ten_list", "TenFields")),
        _pr(5, Severity.MEDIUM),
        id="PR-05-exactly-ten-fields-triggers",
    ),
    pytest.param(
        "large_entity_list_surface",
        lambda: _wide("SmallEntity", 8, _surface("small_list", "SmallEntity")),
        [],
        id="PR-05-nine-fields",
    ),
    pytest.param(
        "large_entity_list_surface",
        lambda: _wide("BigEntity", 12, _surface("big_detail", "BigEntity", "detail")),
        [],
        id="PR-05-non-list-surface",
    ),
    pytest.param("large_entity_list_surface", make_appspec, [], id="PR-05-no-surfaces"),
    pytest.param(
        "large_entity_list_surface",
        lambda: make_appspec(surfaces=[_surface("ghost_list", "Ghost")]),
        [],
        id="PR-05-entity-not-found",
    ),
    # A resolvable view_ref projects the surface down to the view's field count.
    pytest.param(
        "large_entity_list_surface",
        lambda: _wide(
            "Contact",
            20,
            _surface("contact_list", "Contact", view_ref="ContactSummary"),
            views=[
                ViewSpec(
                    name="ContactSummary",
                    source_entity="Contact",
                    fields=[ViewFieldSpec(name=n) for n in ("id", "name", "email")],
                )
            ],
        ),
        [],
        id="PR-05-view-projection-reduces-field-count",
    ),
    pytest.param(
        "large_entity_list_surface",
        lambda: _wide("BigEntity", 10, _surface("big_list", "BigEntity", view_ref="Missing")),
        _pr(5, Severity.MEDIUM),
        id="PR-05-unresolved-view-falls-back-to-entity",
    ),
    # PR-07  entity surfaced beyond the one-per-mode baseline
    # #1356: one surface per mode is the framework baseline, not a hot path.
    pytest.param(
        "heavily_surfaced_entity",
        lambda: _surfaces(*_CRUD),
        [],
        id="PR-07-crud-quartet-not-flagged-1356",
    ),
    # CRUD quartet + two extra list views: excess 2, hot; title carries the count.
    pytest.param(
        "heavily_surfaced_entity",
        lambda: _surfaces(*_CRUD, ("task_board", "Task", "list"), ("task_archive", "Task", "list")),
        _pr(7, Severity.MEDIUM, title_has=("Task", "6")),
        id="PR-07-flags-surfaces-beyond-mode-baseline-1356",
    ),
    pytest.param(
        "heavily_surfaced_entity",
        lambda: _surfaces(*((f"task_view_{i}", "Task", "list") for i in range(5))),
        _pr(7, Severity.MEDIUM, title_has="Task"),
        id="PR-07-flags-five-same-mode-surfaces",
    ),
    pytest.param(
        "heavily_surfaced_entity",
        lambda: _surfaces(_CRUD[0], _CRUD[1], _CRUD[3]),
        [],
        id="PR-07-three-surfaces",
    ),
    pytest.param(
        "heavily_surfaced_entity",
        lambda: _surfaces(
            ("task_list", "Task", "list"),
            ("task_board", "Task", "list"),
            ("task_kanban", "Task", "list"),
            ("task_timeline", "Task", "list"),
            ("user_list", "User", "list"),
            ("user_detail", "User", "view"),
        ),
        _pr(7, title_has="Task"),
        id="PR-07-flags-only-hot-entity",
    ),
    pytest.param("heavily_surfaced_entity", make_appspec, [], id="PR-07-no-surfaces"),
    pytest.param(
        "heavily_surfaced_entity",
        lambda: make_appspec(surfaces=[_surface("dashboard", None)]),
        [],
        id="PR-07-surface-without-entity",
    ),
    # PR-08  multi-step process left on the 24h default timeout
    pytest.param(
        "process_default_timeout",
        lambda: _one_process(timeout_seconds=86400, steps=[MagicMock(), MagicMock()]),
        _pr(8, Severity.LOW, title_has="approve_order", description_has="2 steps"),
        id="PR-08-flags-default-timeout-with-steps",
    ),
    pytest.param(
        "process_default_timeout",
        lambda: _one_process(timeout_seconds=3600, steps=[MagicMock()]),
        [],
        id="PR-08-custom-timeout",
    ),
    pytest.param(
        "process_default_timeout",
        lambda: _one_process(timeout_seconds=86400, steps=[]),
        [],
        id="PR-08-default-timeout-without-steps",
    ),
    pytest.param("process_default_timeout", make_appspec, [], id="PR-08-no-processes"),
]


@pytest.mark.parametrize(("heuristic", "build", "expected"), CASES)
def test_heuristic(
    heuristic: str, build: Callable[[], Any], expected: list[dict[str, Any]]
) -> None:
    assert_findings(getattr(PerformanceResourceAgent(), heuristic)(build()), expected)


def test_run_collects_findings_from_every_heuristic() -> None:
    # One N+1 list surface, two unindexed refs and two default-timeout
    # processes: run() iterates every offender of every heuristic.
    entity = make_entity(
        "Order",
        [
            pk_field(),
            ref_field("customer", "Customer"),
            ref_field("product", "Product"),
            *_three_has_many(),
        ],
    )
    procs = [_process(n, timeout_seconds=86400, steps=[MagicMock()]) for n in ("pa", "pb")]
    result = PerformanceResourceAgent().run(
        make_appspec([entity], surfaces=[_surface("order_list", "Order")], processes=procs)
    )
    assert result.errors == []
    ids = [f.heuristic_id for f in result.findings]
    assert ids.count("PR-01") == 1
    assert ids.count("PR-02") == 2
    assert ids.count("PR-08") == 2
