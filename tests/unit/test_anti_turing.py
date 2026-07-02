"""Tests for Anti-Turing-Complete enforcement."""

import pytest

from dazzle.core.anti_turing import (
    AntiTuringValidator,
    ViolationType,
    validate_dsl_content,
)


class TestAntiTuringValidator:
    """Test the AntiTuringValidator class."""

    @pytest.fixture
    def validator(self) -> AntiTuringValidator:
        return AntiTuringValidator()

    # === Valid DSL Tests ===
    # One contract: legitimate DSL forms produce zero violations.

    @pytest.mark.parametrize(
        "dsl",
        [
            pytest.param(
                """
entity Task "A task":
  id: uuid pk
  title: str(200) required
  completed: bool default=false
  due_date: date optional
""",
                id="entity-declaration",
            ),
            pytest.param(
                """
surface task_list "Task List":
  uses entity Task
  mode: list
  section main:
    field title "Title"
    field completed "Done"
""",
                id="surface-declaration",
            ),
            pytest.param(
                """
workspace dashboard "Dashboard":
  active_tasks:
    source: Task
    filter: completed = false and due_date > today
    sort: priority desc, due_date asc
""",
                id="workspace-with-filter",
            ),
            pytest.param(
                """
surface task_list "Tasks":
  ux:
    attention critical:
      when: days_until(due_date) < 1 and completed = false
      message: "Task is overdue!"
""",
                id="attention-signal",
            ),
            pytest.param(
                """
workspace dashboard:
  metrics:
    aggregate:
      total_tasks: count(id)
      avg_priority: avg(priority)
      max_days: max(days_until(due_date))
""",
                id="aggregate-functions",
            ),
            pytest.param(
                """
entity Invoice:
  id: uuid pk
  title: str(200) required
  amount: decimal(10,2) required
  notes: text optional
  status: enum[draft,sent,paid]
""",
                id="type-annotations",
            ),
            pytest.param(
                # Keywords inside quoted strings should not trigger violations.
                """
entity Task "A task for tracking things":
  id: uuid pk
  description: str(500) required
  # This description might say "if this then that"
""",
                id="quoted-strings-with-keywords",
            ),
            pytest.param(
                # Keywords in comments should be ignored.
                """
# if we need to add more fields, do it here
# for each task, we track the following:
entity Task:
  id: uuid pk
""",
                id="comments-with-keywords",
            ),
            pytest.param(
                # Persona blocks use 'as <identifier>:' syntax (#998 — renamed
                # from `for <identifier>:` to remove the overloaded `for`
                # keyword; bare `for` is a banned-keyword violation again).
                """
surface dashboard:
  ux:
    as ops_engineer:
      scope: all
      purpose: "Full visibility"
    as support_agent:
      scope: assigned
""",
                id="persona-as-block",
            ),
            pytest.param("", id="empty-content"),
            pytest.param(
                """
# This is a comment
# Another comment
# if we had code here, it would be validated
""",
                id="only-comments",
            ),
        ],
    )
    def test_valid_dsl_no_violations(self, validator: AntiTuringValidator, dsl: str) -> None:
        violations = validator.validate(dsl)
        assert violations == [], f"Unexpected violations: {violations}"

    # === Banned Keyword / Pattern / Function-Call Tests ===
    # One contract: Turing-complete constructs produce a violation of the
    # expected type. `keyword` is additionally required in the violation
    # message when not None.

    @pytest.mark.parametrize(
        ("dsl", "expected_type", "keyword"),
        [
            pytest.param(
                """
entity Task:
  id: uuid pk
  status: if completed then "done" else "pending"
""",
                ViolationType.BANNED_KEYWORD,
                "if",
                id="banned-if-keyword",
            ),
            pytest.param(
                """
workspace dashboard:
  tasks:
    for task in tasks:
      display: task.title
""",
                ViolationType.BANNED_KEYWORD,
                "for",
                id="banned-for-keyword",
            ),
            pytest.param(
                """
entity Task:
  id: uuid pk
  while: bool default=false
""",
                ViolationType.BANNED_KEYWORD,
                None,
                id="banned-while-keyword",
            ),
            pytest.param(
                """
def calculate_total(items):
  return sum(items)
""",
                ViolationType.BANNED_KEYWORD,
                "def",
                id="banned-def-keyword",
            ),
            pytest.param(
                """
entity Task:
  compute: lambda x: x * 2
""",
                ViolationType.BANNED_KEYWORD,
                None,
                id="banned-lambda-keyword",
            ),
            pytest.param(
                """
service calculate:
  return total * tax_rate
""",
                ViolationType.BANNED_KEYWORD,
                None,
                id="banned-return-keyword",
            ),
            pytest.param(
                """
entity Task:
  compute: (x) => x * 2
""",
                ViolationType.BANNED_PATTERN,
                None,
                id="banned-arrow-function",
            ),
            pytest.param(
                """
entity Task:
  status: completed ? "done" : "pending"
""",
                ViolationType.BANNED_PATTERN,
                None,
                id="banned-ternary-operator",
            ),
            pytest.param(
                """
workspace dashboard:
  metrics:
    total: calculate_total(items)
""",
                ViolationType.INVALID_FUNCTION_CALL,
                None,
                id="invalid-custom-function",
            ),
            pytest.param(
                """
entity Task:
  hash: sha256(title)
""",
                ViolationType.INVALID_FUNCTION_CALL,
                None,
                id="invalid-arbitrary-function",
            ),
        ],
    )
    def test_banned_construct_fires(
        self,
        validator: AntiTuringValidator,
        dsl: str,
        expected_type: ViolationType,
        keyword: str | None,
    ) -> None:
        violations = validator.validate(dsl)
        assert len(violations) >= 1
        assert any(
            v.type == expected_type and (keyword is None or keyword in v.message.lower())
            for v in violations
        )

    # === Convenience Function Tests ===

    def test_validate_dsl_content_valid(self) -> None:
        """validate_dsl_content should return True for valid DSL."""
        dsl = """
entity Task:
  id: uuid pk
  title: str(200) required
"""
        is_valid, message = validate_dsl_content(dsl)
        assert is_valid is True
        assert "passed" in message.lower()

    def test_validate_dsl_content_invalid(self) -> None:
        """validate_dsl_content should return False for invalid DSL."""
        dsl = """
entity Task:
  id: uuid pk
  compute: if x > 0 then y else z
"""
        is_valid, message = validate_dsl_content(dsl)
        assert is_valid is False
        assert "violation" in message.lower()

    # === Edge Case Tests ===
    # (empty-content / only-comments live as rows in the valid-DSL table above)

    def test_mixed_valid_and_invalid(self, validator: AntiTuringValidator) -> None:
        """Multiple violations should all be caught."""
        dsl = """
entity Task:
  id: uuid pk
  status: if completed then "done" else "pending"
  compute: (x) => x * 2
  process: for item in items
"""
        violations = validator.validate(dsl)
        # Should catch: if, then, else, =>, for
        assert len(violations) >= 3

    def test_case_insensitive_keywords(self, validator: AntiTuringValidator) -> None:
        """Keywords should be caught regardless of case."""
        dsl = """
entity Task:
  status: IF completed THEN "done" ELSE "pending"
"""
        violations = validator.validate(dsl)
        # Should catch IF, THEN, ELSE
        assert len(violations) >= 1

    def test_format_violations(self, validator: AntiTuringValidator) -> None:
        """Violation formatting should produce readable output."""
        dsl = """
entity Task:
  status: if completed then done
"""
        violations = validator.validate(dsl)
        formatted = validator.format_violations(violations)

        assert "violation" in formatted.lower()
        assert "Line" in formatted
        assert "if" in formatted.lower() or "then" in formatted.lower()


# #998 — additions for the as/persona/scope rename + safety tightening.


class TestAntiTuringCycle998:
    """Regression coverage for the #998 carve-out cleanup.

    Ensures the new shape of ALLOWED_PATTERNS / ALLOWED_FUNCTIONS still
    rejects the things it was always meant to reject, and accepts the
    legitimate DSL forms it was wrongly rejecting before."""

    def setup_method(self) -> None:
        from dazzle.core.anti_turing import AntiTuringValidator

        self.v = AntiTuringValidator()

    # ── allow ────────────────────────────────────────────────────────

    def test_role_call_allowed(self) -> None:
        # Used in every permit/scope rule.
        assert not self.v.validate("  list: role(admin)\n")

    def test_persona_call_allowed(self) -> None:
        # Workspace access blocks.
        assert not self.v.validate("  access: persona(engineer, manager)\n")

    def test_via_entity_call_allowed(self) -> None:
        # Junction-EXISTS scope predicate. Entity name is user-defined.
        assert not self.v.validate(
            "  list: via RealmGuardian(guardian = current_user, realm = realm)\n"
        )

    def test_then_block_header_allowed(self) -> None:
        assert not self.v.validate("  then:\n    - outcome\n")

    def test_match_block_header_allowed(self) -> None:
        assert not self.v.validate("  match:\n    - pattern\n")

    def test_on_continue_step_transition_allowed(self) -> None:
        # `continue` is a banned keyword but a valid trigger name in
        # `on <trigger> -> step <name>` declarations.
        assert not self.v.validate("    on continue -> step profile\n")

    def test_config_env_cron_allowed(self) -> None:
        assert not self.v.validate('  url: config("URL")\n')
        assert not self.v.validate('  key: env("KEY")\n')
        assert not self.v.validate('  schedule: cron("0 * * * *")\n')

    def test_regex_in_allowed(self) -> None:
        assert not self.v.validate('  subject: regex("^TICKET-")\n')
        assert not self.v.validate('  to_address: in("a@x", "b@x")\n')

    def test_bucket_allowed(self) -> None:
        assert not self.v.validate("  group_by: bucket(triggered_at, day)\n")

    # ── reject ───────────────────────────────────────────────────────

    def test_for_keyword_still_banned(self) -> None:
        # The persona/scope `for` syntaxes were renamed to `as` — bare
        # `for` is now a banned-keyword violation again, with no
        # remaining carve-outs.
        violations = self.v.validate("for x in items:\n")
        assert any(v.message and "for" in v.message.lower() for v in violations)

    def test_for_persona_no_longer_a_carve_out(self) -> None:
        violations = self.v.validate("  for persona admin:\n")
        assert violations, "old `for persona X:` should now fail"

    def test_then_prefix_does_not_skip_banned_remainder(self) -> None:
        # The cycle-998 prefix-only allowance: `then:` consumes only
        # itself, the rest of the line is still scanned. Pre-fix, the
        # whole line was whitelisted and `while` slipped through.
        violations = self.v.validate("  then: while true do\n")
        assert any(v.message and "while" in v.message.lower() for v in violations), (
            "`while` after `then:` must still be flagged"
        )

    def test_unknown_function_still_banned(self) -> None:
        violations = self.v.validate("  x: calculate(y)\n")
        assert any(v.message and "calculate" in v.message for v in violations)

    def test_javascript_still_banned(self) -> None:
        violations = self.v.validate("  x: f => g\n")
        assert violations  # arrow function pattern
