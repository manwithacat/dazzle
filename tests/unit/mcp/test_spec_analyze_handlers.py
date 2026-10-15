"""Tests for the spec_analyze MCP handlers."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_CONFTEST_PATH = str(Path(__file__).parent / "conftest.py")


def _load_conftest_helper(name: str) -> object:
    """Load a helper from conftest.py by file path (not package import)."""
    spec = importlib.util.spec_from_file_location("_mcp_conftest", _CONFTEST_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, name)


def _import_spec_analyze():
    """Import spec_analyze handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports
    mock_state = MagicMock()
    install_handlers_common_mock = _load_conftest_helper("install_handlers_common_mock")

    handlers_pkg = MagicMock(pytest_plugins=[])
    sys.modules["dazzle.mcp.server.handlers"] = handlers_pkg
    install_handlers_common_mock()
    sys.modules["dazzle.mcp.server.state"] = mock_state

    handlers_dir = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
    )
    # Preload sibling modules used by spec_analyze (relative imports; package is mocked).
    for sibling in ("spec_questions", "spec_lifecycles"):
        sib_spec = importlib.util.spec_from_file_location(
            f"dazzle.mcp.server.handlers.{sibling}",
            handlers_dir / f"{sibling}.py",
        )
        assert sib_spec and sib_spec.loader
        sib_mod = importlib.util.module_from_spec(sib_spec)
        sys.modules[f"dazzle.mcp.server.handlers.{sibling}"] = sib_mod
        setattr(handlers_pkg, sibling, sib_mod)
        sib_spec.loader.exec_module(sib_mod)

    module_path = handlers_dir / "spec_analyze.py"
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.spec_analyze",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
    sys.modules["dazzle.mcp.server.handlers.spec_analyze"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_sa = _import_spec_analyze()

handle_spec_analyze = _sa.handle_spec_analyze


def _op(operation: str, **args) -> dict:
    """Call the spec_analyze tool through its dispatcher."""
    return json.loads(handle_spec_analyze({"operation": operation, **args}))


def _names(items: list[dict]) -> list[str]:
    return [i["name"] for i in items]


OPERATIONS = [
    "discover_entities",
    "identify_lifecycles",
    "extract_personas",
    "surface_rules",
    "generate_questions",
    "refine_spec",
]


@pytest.mark.parametrize("operation", OPERATIONS)
def test_every_operation_requires_spec_text(operation: str) -> None:
    assert _op(operation) == {"error": "spec_text is required"}


def test_unknown_operation() -> None:
    assert _op("unknown_operation") == {
        "error": "Unknown spec_analyze operation: unknown_operation"
    }


# =============================================================================
# discover_entities
# =============================================================================


def test_discover_entities_capitalised_nouns_and_roles_offline_1631() -> None:
    """Capitalised nouns become domain entities (plurals singularised), role words
    become ``user_role`` entities; the extract is marked offline (#1631)."""
    data = _op(
        "discover_entities", spec_text="A Customer places an Order. The Order contains Items."
    )
    # Order among capitalised nouns follows set iteration, so compare as a mapping.
    assert {e["name"]: e["type"] for e in data["entities"]} == {
        "Customer": "user_role",
        "Order": "domain_entity",
        "Item": "domain_entity",
    }
    assert data["extract_mode"] == "offline_deterministic"


def test_discover_entities_finds_belongs_to_relationship() -> None:
    data = _op(
        "discover_entities",
        spec_text="Each Order belongs to a Customer. Orders contain multiple Items.",
    )
    assert {"Order"} == {r["from"] for r in data["relationships"] if r["type"] == "belongs_to"}


# Each case: spec → names that must appear / must not appear (#1353 cases pinned
# on the issue's exact repro spec).
_SPEC_1353 = (
    "A small invoicing tool: clients, invoices with line items, "
    "draft->sent->paid lifecycle, members see only their own client's "
    "invoices, admins see all. Monthly statement email to each client."
)


@pytest.mark.parametrize(
    ("spec", "present", "absent"),
    [
        pytest.param(
            "The System manages Users. This Application is for Teams.",
            {"User", "Team"},
            {"System", "Application"},
            id="skips-common-words",
        ),
        pytest.param(
            _SPEC_1353, set(), {"Small", "Monthly"}, id="no-adjective-false-positives-1353"
        ),
        pytest.param(_SPEC_1353, {"Client", "Invoice"}, set(), id="comma-list-plurals-1353"),
        pytest.param(_SPEC_1353, {"LineItem"}, set(), id="compound-child-entity-1353"),
        pytest.param(_SPEC_1353, {"Member", "Admin"}, set(), id="roles-still-detected-1353"),
        pytest.param(
            "LineItem rows roll up. The total is computed.",
            {"LineItem"},
            set(),
            id="camel-case-counts-sentence-initial-1353",
        ),
        pytest.param(
            "status, address records for each site.",
            set(),
            {"Statu", "Addres"},
            id="non-plural-s-words-not-singularised-1353",
        ),
    ],
)
def test_discover_entities_names(spec: str, present: set, absent: set) -> None:
    names = set(_names(_op("discover_entities", spec_text=spec)["entities"]))
    assert present <= names
    assert not (absent & names)


# =============================================================================
# identify_lifecycles
# =============================================================================


@pytest.mark.parametrize(
    ("spec", "entity", "states"),
    [
        pytest.param(
            "Orders are created and then shipped to customers.",
            "Order",
            ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"],
            id="order-pattern",
        ),
        pytest.param(
            "Requests can be submitted and approved or rejected.",
            "Request",
            ["draft", "submitted", "pending", "approved", "rejected", "completed"],
            id="request-pattern",
        ),
        pytest.param(
            "Tasks are assigned to team members and completed.",
            "Task",
            ["pending", "assigned", "in_progress", "completed", "blocked"],
            id="task-pattern",
        ),
    ],
)
def test_identify_lifecycles_pattern_match(spec: str, entity: str, states: list[str]) -> None:
    lifecycles = _op("identify_lifecycles", spec_text=spec, entities=[entity])["lifecycles"]
    assert lifecycles == [
        {"entity": entity, "status_field": "status", "states": states, "source": "pattern_match"}
    ]


def test_identify_lifecycles_detects_transition_words() -> None:
    data = _op(
        "identify_lifecycles",
        spec_text="Users can submit, approve, reject, or cancel items.",
        entities=[],
    )
    assert data["detected_transitions"] == ["approve", "cancel", "reject", "submit"]


# #1353: explicit arrow chains mirror DSL transitions syntax and win over the
# canned pattern guess; a chain with no named entity is attributed to UNKNOWN.
@pytest.mark.parametrize(
    ("spec", "entities", "entity", "states"),
    [
        pytest.param(
            "Invoices follow a draft->sent->paid lifecycle.",
            ["Invoice"],
            "Invoice",
            ["draft", "sent", "paid"],
            id="ascii-arrow-attributed-1353",
        ),
        pytest.param(
            "Tickets: open → triaged → closed.",
            ["Ticket"],
            "Ticket",
            ["open", "triaged", "closed"],
            id="unicode-arrow-1353",
        ),
        pytest.param(
            "Orders move quoted->packed->shipped.",
            ["Order"],
            "Order",
            ["quoted", "packed", "shipped"],
            id="arrow-chain-beats-pattern-guess-1353",
        ),
        pytest.param(
            "Everything is draft->live eventually.",
            [],
            "UNKNOWN",
            ["draft", "live"],
            id="chain-without-entity-unattributed-1353",
        ),
    ],
)
def test_arrow_chain_lifecycles(spec: str, entities: list, entity: str, states: list) -> None:
    lifecycles = _op("identify_lifecycles", spec_text=spec, entities=entities)["lifecycles"]
    chains = [lc for lc in lifecycles if lc.get("source") == "arrow_chain"]
    assert [(c["entity"], c["states"]) for c in chains] == [(entity, states)]
    # The chain is the only lifecycle for its entity — no pattern-match duplicate.
    assert len([lc for lc in lifecycles if lc["entity"] == entity]) == 1


# =============================================================================
# extract_personas / surface_rules / generate_questions / refine_spec
# =============================================================================


# Admin is always present: explicitly, or added as an implicit platform administrator.
@pytest.mark.parametrize(
    ("spec", "personas"),
    [
        pytest.param(
            "Administrators can manage all users and settings.", ["Admin", "User"], id="admin"
        ),
        pytest.param("Users can create and view their own content.", ["User", "Admin"], id="user"),
        pytest.param(
            "Customers can browse products and place orders.", ["Customer", "Admin"], id="customer"
        ),
    ],
)
def test_extract_personas(spec: str, personas: list[str]) -> None:
    assert _names(_op("extract_personas", spec_text=spec)["personas"]) == personas


@pytest.mark.parametrize(
    ("spec", "rule", "dsl_hint"),
    [
        pytest.param(
            "Users must verify their email before placing orders.",
            "must verify their email before placing orders",
            "Consider invariant or guard",
            id="must",
        ),
        pytest.param(
            "Users cannot delete orders after they are shipped.",
            "cannot delete orders after they are shipped",
            "Consider invariant with negation",
            id="cannot",
        ),
        pytest.param(
            "Only admins can access the settings page.",
            "only admins can access the settings page",
            "Consider permission or guard",
            id="only",
        ),
    ],
)
def test_surface_rules(spec: str, rule: str, dsl_hint: str) -> None:
    assert _op("surface_rules", spec_text=spec)["business_rules"] == [
        {"type": "constraint", "rule": rule, "dsl_hint": dsl_hint}
    ]


@pytest.mark.parametrize(
    ("spec", "topics"),
    [
        pytest.param(
            "The app should handle payments and user authentication.",
            ["cardinality"],
            id="payment-user-cardinality",
        ),
        pytest.param("The system should be fast and handle many users.", [], id="nothing-to-ask"),
    ],
)
def test_generate_questions(spec: str, topics: list[str]) -> None:
    questions = _op("generate_questions", spec_text=spec)["questions"]
    assert [q["topic"] for q in questions] == topics


def test_refine_spec_structures_spec_and_records_answers() -> None:
    answers = {"auth_method": "email_password", "multi_tenant": False}
    data = _op("refine_spec", spec_text="A simple todo app.", answers=answers)
    assert data["original_spec"] == "A simple todo app."
    assert _names(data["entities"]) == ["Todo"]
    assert data["state_machines"][0]["entity"] == "Todo"
    assert data["answered_questions"] == answers


class TestChromeEntities1631:
    """#1631 — refuse markdown table chrome as domain entities."""

    SPEND_SPEC = """
# Spend Desk

Single-org spend request app with three job desks.

| Field | Type | Optional | Display | Raise |
|-------|------|----------|---------|-------|
| amount | money | no | Amount | - |
| status | enum | no | Status | - |

## Personas
- Employee submits a SpendRequest
- Manager approves or rejects
- Finance pays approved requests

## Pipeline
Employee sees draft and in-flight lists for their SpendRequest rows.
"""

    def test_refuses_markdown_table_chrome(self) -> None:
        data = _op("discover_entities", spec_text=self.SPEND_SPEC)
        names = {e["name"] for e in data.get("entities", [])}
        chrome = {"Optional", "Field", "Display", "Raise", "Type", "Amount", "Status", "Statu"}
        assert not (names & chrome), f"chrome leaked into entities: {names & chrome}"
        assert {"SpendRequest", "Employee"} <= names

    def test_strip_markdown_tables_helper(self) -> None:
        strip_fn = _sa._strip_markdown_tables
        stripped = strip_fn("Hello\n| Field | Type |\n|-------|------|\n| x | y |\nWorld")
        assert "Field" not in stripped
        assert "Hello" in stripped
        assert "World" in stripped
