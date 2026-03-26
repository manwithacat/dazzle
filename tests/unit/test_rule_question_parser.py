"""Tests for rule and question DSL construct parsing (v0.41.0 Convergent BDD)."""

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import QuestionStatus, RuleKind, RuleOrigin, RuleStatus

# ── Helpers ───────────────────────────────────────────────────────────


def _parse(dsl_body: str):
    """Parse a DSL snippet wrapped in a test module."""
    full = f'module test_mod\napp test_app "Test"\n\n{dsl_body}'
    _mod, _app, _title, _cfg, _uses, fragment = parse_dsl(full, "test.dsl")
    return fragment


# ── Rule parsing ──────────────────────────────────────────────────────


class TestRuleParsing:
    def test_minimal_rule(self) -> None:
        fragment = _parse("""
rule RULE-001 "Minimal rule":
  kind: constraint
""")
        assert len(fragment.rules) == 1
        r = fragment.rules[0]
        assert r.rule_id == "RULE-001"
        assert r.title == "Minimal rule"
        assert r.kind == RuleKind.CONSTRAINT

    def test_full_rule(self) -> None:
        fragment = _parse("""
rule RULE-C-001 "Customer sees next action":
  kind: constraint
  origin: top_down
  invariant: customer dashboard shows actionable items
  scope: [Customer, Task]
  status: accepted
""")
        assert len(fragment.rules) == 1
        r = fragment.rules[0]
        assert r.rule_id == "RULE-C-001"
        assert r.title == "Customer sees next action"
        assert r.kind == RuleKind.CONSTRAINT
        assert r.origin == RuleOrigin.TOP_DOWN
        assert r.invariant == "customer dashboard shows actionable items"
        assert r.scope == ["Customer", "Task"]
        assert r.status == RuleStatus.ACCEPTED

    def test_rule_kinds(self) -> None:
        for kind in ("constraint", "precondition", "authorization", "derivation"):
            fragment = _parse(f"""
rule R-001 "Test":
  kind: {kind}
""")
            assert fragment.rules[0].kind == RuleKind(kind)

    def test_rule_origins(self) -> None:
        for origin in ("top_down", "bottom_up"):
            fragment = _parse(f"""
rule R-001 "Test":
  origin: {origin}
""")
            assert fragment.rules[0].origin == RuleOrigin(origin)

    def test_rule_with_description(self) -> None:
        fragment = _parse("""
rule R-001 "Test rule":
  "This is a longer description"
  kind: precondition
""")
        r = fragment.rules[0]
        assert r.description == "This is a longer description"
        assert r.kind == RuleKind.PRECONDITION

    def test_rule_defaults(self) -> None:
        """Rule with no optional fields gets correct defaults."""
        fragment = _parse("""
rule R-001 "Bare rule":
  invariant: something must hold
""")
        r = fragment.rules[0]
        assert r.kind == RuleKind.CONSTRAINT  # default
        assert r.origin == RuleOrigin.TOP_DOWN  # default
        assert r.status == RuleStatus.DRAFT  # default
        assert r.scope == []

    def test_rule_source_location(self) -> None:
        fragment = _parse("""
rule R-001 "Located":
  kind: derivation
""")
        assert fragment.rules[0].source is not None

    def test_invalid_kind_raises(self) -> None:
        with pytest.raises(Exception, match="Invalid rule kind"):
            _parse("""
rule R-001 "Bad":
  kind: nonsense
""")

    def test_invalid_origin_raises(self) -> None:
        with pytest.raises(Exception, match="Invalid rule origin"):
            _parse("""
rule R-001 "Bad":
  origin: sideways
""")

    def test_multiple_rules(self) -> None:
        fragment = _parse("""
rule R-001 "First":
  kind: constraint

rule R-002 "Second":
  kind: authorization
""")
        assert len(fragment.rules) == 2
        assert fragment.rules[0].rule_id == "R-001"
        assert fragment.rules[1].rule_id == "R-002"


# ── Question parsing ─────────────────────────────────────────────────


class TestQuestionParsing:
    def test_minimal_question(self) -> None:
        fragment = _parse("""
question Q-001 "Open question":
  status: open
""")
        assert len(fragment.questions) == 1
        q = fragment.questions[0]
        assert q.question_id == "Q-001"
        assert q.title == "Open question"
        assert q.status == QuestionStatus.OPEN

    def test_full_question(self) -> None:
        fragment = _parse("""
question Q-001 "Which approval workflow applies?":
  blocks: [RULE-A-002, ST-014]
  raised_by: reviewer
  status: open
""")
        q = fragment.questions[0]
        assert q.question_id == "Q-001"
        assert q.title == "Which approval workflow applies?"
        assert q.blocks == ["RULE-A-002", "ST-014"]
        assert q.raised_by == "reviewer"
        assert q.status == QuestionStatus.OPEN

    def test_question_statuses(self) -> None:
        for status in ("open", "resolved", "deferred"):
            fragment = _parse(f"""
question Q-001 "Test":
  status: {status}
""")
            assert fragment.questions[0].status == QuestionStatus(status)

    def test_resolved_question_with_resolution(self) -> None:
        fragment = _parse("""
question Q-001 "What threshold?":
  status: resolved
  resolution: "Use 10000 GBP as the threshold"
""")
        q = fragment.questions[0]
        assert q.status == QuestionStatus.RESOLVED
        assert q.resolution == "Use 10000 GBP as the threshold"

    def test_question_with_description(self) -> None:
        fragment = _parse("""
question Q-001 "Test":
  "More context about the gap"
  raised_by: admin
""")
        q = fragment.questions[0]
        assert q.description == "More context about the gap"

    def test_question_defaults(self) -> None:
        fragment = _parse("""
question Q-001 "Bare question":
  raised_by: tester
""")
        q = fragment.questions[0]
        assert q.status == QuestionStatus.OPEN  # default
        assert q.blocks == []
        assert q.resolution is None

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(Exception, match="Invalid question status"):
            _parse("""
question Q-001 "Bad":
  status: invalid
""")

    def test_multiple_questions(self) -> None:
        fragment = _parse("""
question Q-001 "First":
  status: open

question Q-002 "Second":
  status: deferred
""")
        assert len(fragment.questions) == 2
        assert fragment.questions[0].question_id == "Q-001"
        assert fragment.questions[1].question_id == "Q-002"


# ── Mixed constructs ─────────────────────────────────────────────────


class TestMixedConstructs:
    def test_rules_and_questions_together(self) -> None:
        fragment = _parse("""
rule R-001 "Domain invariant":
  kind: constraint
  scope: [Invoice]

question Q-001 "Open question":
  blocks: [R-001]
  raised_by: reviewer
  status: open
""")
        assert len(fragment.rules) == 1
        assert len(fragment.questions) == 1
        assert fragment.questions[0].blocks == ["R-001"]

    def test_rules_with_stories_and_entities(self) -> None:
        fragment = _parse("""
entity Invoice "Invoice":
  id: uuid pk
  amount: decimal(10,2)

story ST-001 "Submit invoice":
  actor: Staff
  trigger: form_submitted
  scope: [Invoice]

rule R-001 "Invoice must have amount":
  kind: precondition
  scope: [Invoice]
""")
        assert len(fragment.entities) == 1
        assert len(fragment.stories) == 1
        assert len(fragment.rules) == 1
