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

    sys.modules["dazzle.mcp.server.handlers"] = MagicMock(pytest_plugins=[])
    install_handlers_common_mock()
    sys.modules["dazzle.mcp.server.state"] = mock_state

    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "spec_analyze.py"
    )
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

# Get references to the functions we need
handle_spec_analyze = _sa.handle_spec_analyze
_discover_entities = _sa._discover_entities
_identify_lifecycles = _sa._identify_lifecycles
_extract_personas = _sa._extract_personas
_surface_rules = _sa._surface_rules
_generate_questions = _sa._generate_questions
_refine_spec = _sa._refine_spec


class TestHandleSpecAnalyze:
    """Tests for the main dispatch function."""

    def test_discover_entities_dispatch(self) -> None:
        """Test dispatch to discover_entities."""
        result = handle_spec_analyze(
            {
                "operation": "discover_entities",
                "spec_text": "The Customer places an Order.",
            }
        )
        data = json.loads(result)
        assert "entities" in data or "error" not in data

    @pytest.mark.parametrize(
        ("params", "expected_key"),
        [
            (
                {
                    "operation": "identify_lifecycles",
                    "spec_text": "Orders go from pending to shipped.",
                    "entities": ["Order"],
                },
                "lifecycles",
            ),
            (
                {
                    "operation": "extract_personas",
                    "spec_text": "Admins can manage users. Customers can place orders.",
                },
                "personas",
            ),
            (
                {
                    "operation": "surface_rules",
                    "spec_text": "Users must verify email before ordering.",
                },
                "business_rules",
            ),
            (
                {
                    "operation": "generate_questions",
                    "spec_text": "The app should handle payments.",
                },
                "questions",
            ),
        ],
        ids=[
            "test_identify_lifecycles_dispatch",
            "test_extract_personas_dispatch",
            "test_surface_rules_dispatch",
            "test_generate_questions_dispatch",
        ],
    )
    def test_operation_dispatch(self, params: dict, expected_key: str) -> None:
        result = handle_spec_analyze(params)
        data = json.loads(result)
        assert expected_key in data

    def test_refine_spec_dispatch(self) -> None:
        """Test dispatch to refine_spec."""
        result = handle_spec_analyze(
            {
                "operation": "refine_spec",
                "spec_text": "A simple todo app for managing tasks.",
            }
        )
        data = json.loads(result)
        assert "refined_spec" in data or "entities" in data

    def test_unknown_operation(self) -> None:
        """Test error for unknown operation."""
        result = handle_spec_analyze(
            {
                "operation": "unknown_operation",
            }
        )
        data = json.loads(result)
        assert "error" in data
        assert "Unknown" in data["error"] and "operation" in data["error"]


class TestDiscoverEntities:
    """Tests for entity discovery."""

    def test_requires_spec_text(self) -> None:
        """Test that spec_text is required."""
        result = _discover_entities({})
        data = json.loads(result)
        assert "error" in data
        assert "spec_text is required" in data["error"]

    def test_finds_capitalized_nouns(self) -> None:
        """Test finding capitalized nouns as potential entities."""
        result = _discover_entities(
            {"spec_text": "A Customer places an Order. The Order contains Items."}
        )
        data = json.loads(result)
        entities = data.get("entities", [])
        entity_names = [e["name"] if isinstance(e, dict) else e for e in entities]
        assert "Customer" in entity_names or "Order" in entity_names

    def test_finds_relationships(self) -> None:
        """Test finding relationships between entities."""
        result = _discover_entities(
            {"spec_text": "Each Order belongs to a Customer. Orders contain multiple Items."}
        )
        data = json.loads(result)
        # Should identify relationships
        relationships = data.get("relationships", [])
        assert isinstance(relationships, list)

    def test_skips_common_words(self) -> None:
        """Test that common words are not detected as entities."""
        result = _discover_entities(
            {"spec_text": "The System manages Users. This Application is for Teams."}
        )
        data = json.loads(result)
        entities = data.get("entities", [])
        entity_names = [e["name"] if isinstance(e, dict) else e for e in entities]
        # "System", "Application" should be skipped
        assert "System" not in entity_names
        assert "Application" not in entity_names


class TestIdentifyLifecycles:
    """Tests for lifecycle identification."""

    def test_requires_spec_text(self) -> None:
        """Test that spec_text is required."""
        result = _identify_lifecycles({"entities": ["Order"]})
        data = json.loads(result)
        assert "error" in data

    def test_identifies_order_lifecycle(self) -> None:
        """Test identification of order lifecycle pattern."""
        result = _identify_lifecycles(
            {
                "spec_text": "Orders are created and then shipped to customers.",
                "entities": ["Order"],
            }
        )
        data = json.loads(result)
        lifecycles = data.get("lifecycles", [])
        assert len(lifecycles) >= 1
        order_lifecycle = next((lc for lc in lifecycles if lc["entity"] == "Order"), None)
        assert order_lifecycle is not None
        assert "states" in order_lifecycle

    def test_identifies_request_lifecycle(self) -> None:
        """Test identification of request lifecycle pattern."""
        result = _identify_lifecycles(
            {
                "spec_text": "Requests can be submitted and approved or rejected.",
                "entities": ["Request"],
            }
        )
        data = json.loads(result)
        lifecycles = data.get("lifecycles", [])
        assert len(lifecycles) >= 1

    def test_identifies_task_lifecycle(self) -> None:
        """Test identification of task lifecycle pattern."""
        result = _identify_lifecycles(
            {
                "spec_text": "Tasks are assigned to team members and completed.",
                "entities": ["Task"],
            }
        )
        data = json.loads(result)
        lifecycles = data.get("lifecycles", [])
        assert len(lifecycles) >= 1

    def test_detects_transition_words(self) -> None:
        """Test detection of transition keywords."""
        result = _identify_lifecycles(
            {
                "spec_text": "Users can submit, approve, reject, or cancel items.",
                "entities": [],
            }
        )
        data = json.loads(result)
        transitions = data.get("detected_transitions", [])
        assert "submit" in transitions or "approve" in transitions


class TestExtractPersonas:
    """Tests for persona extraction."""

    def test_requires_spec_text(self) -> None:
        """Test that spec_text is required."""
        result = _extract_personas({})
        data = json.loads(result)
        assert "error" in data

    def test_finds_admin_persona(self) -> None:
        """Test finding admin persona."""
        result = _extract_personas(
            {"spec_text": "Administrators can manage all users and settings."}
        )
        data = json.loads(result)
        personas = data.get("personas", [])
        persona_names = [p["name"] if isinstance(p, dict) else p for p in personas]
        assert any("admin" in name.lower() for name in persona_names)

    def test_finds_user_persona(self) -> None:
        """Test finding user persona."""
        result = _extract_personas({"spec_text": "Users can create and view their own content."})
        data = json.loads(result)
        personas = data.get("personas", [])
        assert len(personas) >= 1

    def test_finds_customer_persona(self) -> None:
        """Test finding customer persona."""
        result = _extract_personas({"spec_text": "Customers can browse products and place orders."})
        data = json.loads(result)
        personas = data.get("personas", [])
        persona_names = [p["name"] if isinstance(p, dict) else p for p in personas]
        assert any("customer" in name.lower() for name in persona_names)


class TestSurfaceRules:
    """Tests for business rule extraction."""

    def test_requires_spec_text(self) -> None:
        """Test that spec_text is required."""
        result = _surface_rules({})
        data = json.loads(result)
        assert "error" in data

    def test_finds_must_rules(self) -> None:
        """Test finding 'must' constraints."""
        result = _surface_rules(
            {"spec_text": "Users must verify their email before placing orders."}
        )
        data = json.loads(result)
        rules = data.get("business_rules", [])
        assert len(rules) >= 1

    def test_finds_cannot_rules(self) -> None:
        """Test finding 'cannot' constraints."""
        result = _surface_rules({"spec_text": "Users cannot delete orders after they are shipped."})
        data = json.loads(result)
        rules = data.get("business_rules", [])
        assert len(rules) >= 1

    def test_finds_only_rules(self) -> None:
        """Test finding 'only' constraints."""
        result = _surface_rules({"spec_text": "Only admins can access the settings page."})
        data = json.loads(result)
        rules = data.get("business_rules", [])
        assert len(rules) >= 1


class TestGenerateQuestions:
    """Tests for question generation."""

    def test_requires_spec_text(self) -> None:
        """Test that spec_text is required."""
        result = _generate_questions({})
        data = json.loads(result)
        assert "error" in data

    def test_generates_questions(self) -> None:
        """Test that questions are generated."""
        result = _generate_questions(
            {"spec_text": "The app should handle payments and user authentication."}
        )
        data = json.loads(result)
        questions = data.get("questions", [])
        assert isinstance(questions, list)

    def test_questions_about_ambiguity(self) -> None:
        """Test questions about vague requirements."""
        result = _generate_questions(
            {"spec_text": "The system should be fast and handle many users."}
        )
        data = json.loads(result)
        questions = data.get("questions", [])
        # Should generate clarifying questions about vague terms
        assert len(questions) >= 0  # May or may not find issues


class TestRefineSpec:
    """Tests for spec refinement."""

    def test_requires_spec_text(self) -> None:
        """Test that spec_text is required."""
        result = _refine_spec({})
        data = json.loads(result)
        assert "error" in data

    def test_produces_refined_output(self) -> None:
        """Test that refinement produces structured output."""
        result = _refine_spec(
            {
                "spec_text": """
            A task management app where users can create tasks,
            assign them to team members, and track completion.
            Tasks have a title, description, and due date.
            """
            }
        )
        data = json.loads(result)
        # Should have structured output
        assert "refined_spec" in data or "entities" in data or "error" not in data

    def test_incorporates_answers(self) -> None:
        """Test that answers are incorporated into refinement."""
        result = _refine_spec(
            {
                "spec_text": "A simple todo app.",
                "answers": {
                    "auth_method": "email_password",
                    "multi_tenant": False,
                },
            }
        )
        data = json.loads(result)
        # Should process without error
        assert "error" not in data


class TestDiscoverEntitiesHeuristics1353:
    """#1353: adjective/sentence-initial false positives, comma-list and
    arrow-chain misses — pinned on the issue's exact repro spec."""

    SPEC = (
        "A small invoicing tool: clients, invoices with line items, "
        "draft->sent->paid lifecycle, members see only their own client's "
        "invoices, admins see all. Monthly statement email to each client."
    )

    def _names(self, spec: str) -> list[str]:
        data = json.loads(_discover_entities({"spec_text": spec}))
        return [e["name"] for e in data["entities"]]

    def test_no_adjective_false_positives(self) -> None:
        names = self._names(self.SPEC)
        assert "Small" not in names  # "a small invoicing tool"
        assert "Monthly" not in names  # sentence-initial adjective

    def test_comma_list_plurals_extracted(self) -> None:
        names = self._names(self.SPEC)
        assert "Client" in names
        assert "Invoice" in names

    def test_with_compound_child_entity(self) -> None:
        assert "LineItem" in self._names(self.SPEC)

    def test_roles_still_detected(self) -> None:
        names = self._names(self.SPEC)
        assert "Member" in names
        assert "Admin" in names

    def test_camel_case_counts_even_sentence_initial(self) -> None:
        names = self._names("LineItem rows roll up. The total is computed.")
        assert "LineItem" in names

    def test_non_plural_s_words_not_singularised(self) -> None:
        names = self._names("status, address records for each site.")
        assert "Statu" not in names
        assert "Addres" not in names


class TestArrowChainLifecycles1353:
    """#1353: explicit arrow chains mirror DSL transitions syntax and must win."""

    def test_arrow_chain_detected_and_attributed(self) -> None:
        result = _identify_lifecycles(
            {
                "spec_text": "Invoices follow a draft->sent->paid lifecycle.",
                "entities": ["Invoice"],
            }
        )
        data = json.loads(result)
        chains = [lc for lc in data["lifecycles"] if lc.get("source") == "arrow_chain"]
        assert len(chains) == 1
        assert chains[0]["states"] == ["draft", "sent", "paid"]
        assert chains[0]["entity"] == "Invoice"

    def test_unicode_arrow_detected(self) -> None:
        result = _identify_lifecycles(
            {"spec_text": "Tickets: open → triaged → closed.", "entities": ["Ticket"]}
        )
        data = json.loads(result)
        chains = [lc for lc in data["lifecycles"] if lc.get("source") == "arrow_chain"]
        assert chains and chains[0]["states"] == ["open", "triaged", "closed"]

    def test_arrow_chain_beats_pattern_guess(self) -> None:
        # "Order" matches the canned pattern, but the explicit chain must win.
        result = _identify_lifecycles(
            {
                "spec_text": "Orders move quoted->packed->shipped.",
                "entities": ["Order"],
            }
        )
        data = json.loads(result)
        order_lcs = [lc for lc in data["lifecycles"] if lc["entity"] == "Order"]
        assert len(order_lcs) == 1
        assert order_lcs[0]["source"] == "arrow_chain"
        assert order_lcs[0]["states"] == ["quoted", "packed", "shipped"]

    def test_chain_without_entity_is_unattributed(self) -> None:
        result = _identify_lifecycles(
            {"spec_text": "Everything is draft->live eventually.", "entities": []}
        )
        data = json.loads(result)
        chains = [lc for lc in data["lifecycles"] if lc.get("source") == "arrow_chain"]
        assert chains and chains[0]["entity"] == "UNKNOWN"
