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

    def test_valid_entity_declaration(self, validator: AntiTuringValidator) -> None:
        """Entity declarations should pass validation."""
        dsl = """
entity Task "A task":
  id: uuid pk
  title: str(200) required
  completed: bool default=false
  due_date: date optional
"""
        violations = validator.validate(dsl)
        assert violations == [], f"Unexpected violations: {violations}"

    def test_valid_surface_declaration(self, validator: AntiTuringValidator) -> None:
        """Surface declarations should pass validation."""
        dsl = """
surface task_list "Task List":
  uses entity Task
  mode: list
  section main:
    field title "Title"
    field completed "Done"
"""
        violations = validator.validate(dsl)
        assert violations == [], f"Unexpected violations: {violations}"

    def test_valid_workspace_with_filter(self, validator: AntiTuringValidator) -> None:
        """Workspace declarations with filters should pass validation."""
        dsl = """
workspace dashboard "Dashboard":
  active_tasks:
    source: Task
    filter: completed = false and due_date > today
    sort: priority desc, due_date asc
"""
        violations = validator.validate(dsl)
        assert violations == [], f"Unexpected violations: {violations}"

    def test_valid_attention_signal(self, validator: AntiTuringValidator) -> None:
        """Attention signals with conditions should pass validation."""
        dsl = """
surface task_list "Tasks":
  ux:
    attention critical:
      when: days_until(due_date) < 1 and completed = false
      message: "Task is overdue!"
"""
        violations = validator.validate(dsl)
        assert violations == [], f"Unexpected violations: {violations}"

    def test_valid_aggregate_functions(self, validator: AntiTuringValidator) -> None:
        """Allowed aggregate functions should pass validation."""
        dsl = """
workspace dashboard:
  metrics:
    aggregate:
      total_tasks: count(id)
      avg_priority: avg(priority)
      max_days: max(days_until(due_date))
"""
        violations = validator.validate(dsl)
        assert violations == [], f"Unexpected violations: {violations}"

    def test_valid_type_annotations(self, validator: AntiTuringValidator) -> None:
        """Type annotations with parentheses should pass validation."""
        dsl = """
entity Invoice:
  id: uuid pk
  title: str(200) required
  amount: decimal(10,2) required
  notes: text optional
  status: enum[draft,sent,paid]
"""
        violations = validator.validate(dsl)
        assert violations == [], f"Unexpected violations: {violations}"

    def test_valid_quoted_strings_with_keywords(self, validator: AntiTuringValidator) -> None:
        """Keywords inside quoted strings should not trigger violations."""
        dsl = """
entity Task "A task for tracking things":
  id: uuid pk
  description: str(500) required
  # This description might say "if this then that"
"""
        violations = validator.validate(dsl)
        assert violations == [], f"Unexpected violations: {violations}"

    def test_valid_comments_with_keywords(self, validator: AntiTuringValidator) -> None:
        """Keywords in comments should be ignored."""
        dsl = """
# if we need to add more fields, do it here
# for each task, we track the following:
entity Task:
  id: uuid pk
"""
        violations = validator.validate(dsl)
        assert violations == [], f"Unexpected violations: {violations}"

    def test_valid_persona_block(self, validator: AntiTuringValidator) -> None:
        """Persona blocks using 'for <identifier>:' syntax should pass."""
        dsl = """
surface dashboard:
  ux:
    for ops_engineer:
      scope: all
      purpose: "Full visibility"
    for support_agent:
      scope: assigned
"""
        violations = validator.validate(dsl)
        assert violations == [], f"Unexpected violations: {violations}"

    # === Banned Keyword Tests ===

    def test_banned_if_keyword(self, validator: AntiTuringValidator) -> None:
        """'if' keyword should trigger violation."""
        dsl = """
entity Task:
  id: uuid pk
  status: if completed then "done" else "pending"
"""
        violations = validator.validate(dsl)
        assert len(violations) >= 1
        assert any(
            v.type == ViolationType.BANNED_KEYWORD and "if" in v.message.lower() for v in violations
        )

    def test_banned_for_keyword(self, validator: AntiTuringValidator) -> None:
        """'for' keyword should trigger violation."""
        dsl = """
workspace dashboard:
  tasks:
    for task in tasks:
      display: task.title
"""
        violations = validator.validate(dsl)
        assert len(violations) >= 1
        assert any(
            v.type == ViolationType.BANNED_KEYWORD and "for" in v.message.lower()
            for v in violations
        )

    def test_banned_while_keyword(self, validator: AntiTuringValidator) -> None:
        """'while' keyword should trigger violation."""
        dsl = """
entity Task:
  id: uuid pk
  while: bool default=false
"""
        violations = validator.validate(dsl)
        assert len(violations) >= 1
        assert any(v.type == ViolationType.BANNED_KEYWORD for v in violations)

    def test_banned_def_keyword(self, validator: AntiTuringValidator) -> None:
        """'def' keyword should trigger violation."""
        dsl = """
def calculate_total(items):
  return sum(items)
"""
        violations = validator.validate(dsl)
        assert len(violations) >= 1
        assert any(
            v.type == ViolationType.BANNED_KEYWORD and "def" in v.message.lower()
            for v in violations
        )

    def test_banned_lambda_keyword(self, validator: AntiTuringValidator) -> None:
        """'lambda' keyword should trigger violation."""
        dsl = """
entity Task:
  compute: lambda x: x * 2
"""
        violations = validator.validate(dsl)
        assert len(violations) >= 1
        assert any(v.type == ViolationType.BANNED_KEYWORD for v in violations)

    def test_banned_return_keyword(self, validator: AntiTuringValidator) -> None:
        """'return' keyword should trigger violation."""
        dsl = """
service calculate:
  return total * tax_rate
"""
        violations = validator.validate(dsl)
        assert len(violations) >= 1
        assert any(v.type == ViolationType.BANNED_KEYWORD for v in violations)

    # === Banned Pattern Tests ===

    def test_banned_arrow_function(self, validator: AntiTuringValidator) -> None:
        """Arrow function syntax should trigger violation."""
        dsl = """
entity Task:
  compute: (x) => x * 2
"""
        violations = validator.validate(dsl)
        assert len(violations) >= 1
        assert any(v.type == ViolationType.BANNED_PATTERN for v in violations)

    def test_banned_ternary_operator(self, validator: AntiTuringValidator) -> None:
        """Ternary operator should trigger violation."""
        dsl = """
entity Task:
  status: completed ? "done" : "pending"
"""
        violations = validator.validate(dsl)
        assert len(violations) >= 1
        assert any(v.type == ViolationType.BANNED_PATTERN for v in violations)

    # === Invalid Function Call Tests ===

    def test_invalid_custom_function(self, validator: AntiTuringValidator) -> None:
        """Custom function calls should trigger violation."""
        dsl = """
workspace dashboard:
  metrics:
    total: calculate_total(items)
"""
        violations = validator.validate(dsl)
        assert len(violations) >= 1
        assert any(v.type == ViolationType.INVALID_FUNCTION_CALL for v in violations)

    def test_invalid_arbitrary_function(self, validator: AntiTuringValidator) -> None:
        """Arbitrary function calls should trigger violation."""
        dsl = """
entity Task:
  hash: sha256(title)
"""
        violations = validator.validate(dsl)
        assert len(violations) >= 1
        assert any(v.type == ViolationType.INVALID_FUNCTION_CALL for v in violations)

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

    def test_empty_content(self, validator: AntiTuringValidator) -> None:
        """Empty content should pass validation."""
        violations = validator.validate("")
        assert violations == []

    def test_only_comments(self, validator: AntiTuringValidator) -> None:
        """Content with only comments should pass validation."""
        dsl = """
# This is a comment
# Another comment
# if we had code here, it would be validated
"""
        violations = validator.validate(dsl)
        assert violations == []

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
