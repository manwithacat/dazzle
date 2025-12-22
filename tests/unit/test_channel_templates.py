"""
Unit tests for DAZZLE messaging template engine (v0.9.0).

Tests the restricted Jinja-ish template syntax.
Refactored to use parameterization for reduced redundancy.
"""

import pytest

from dazzle_dnr_back.channels.templates import (
    TemplateSyntaxError,
    extract_variables,
    render_template,
    validate_template,
)


class TestBasicInterpolation:
    """Tests for basic variable interpolation."""

    @pytest.mark.parametrize(
        "template,context,expected",
        [
            ("Hello {{ name }}!", {"name": "World"}, "Hello World!"),
            (
                "Hello {{ user.name }}!",
                {"user": {"name": "John"}},
                "Hello John!",
            ),
            (
                "Order: {{ order.customer.address.city }}",
                {"order": {"customer": {"address": {"city": "London"}}}},
                "Order: London",
            ),
            ("Hello {{ name }}!", {}, "Hello !"),
            ("Value: {{ value }}", {"value": None}, "Value: "),
            (
                "{{ greeting }}, {{ name }}! Your order #{{ order_num }} is ready.",
                {"greeting": "Hello", "name": "John", "order_num": "1234"},
                "Hello, John! Your order #1234 is ready.",
            ),
            ("{{  name  }}", {"name": "Test"}, "Test"),
        ],
        ids=[
            "simple_variable",
            "dotted_path",
            "deep_nesting",
            "missing_variable",
            "none_value",
            "multiple_variables",
            "whitespace_in_braces",
        ],
    )
    def test_interpolation(self, template: str, context: dict, expected: str) -> None:
        """Test variable interpolation."""
        result = render_template(template, context)
        assert result == expected


class TestConditionals:
    """Tests for conditional blocks."""

    @pytest.mark.parametrize(
        "template,context,expected",
        [
            ("{% if show %}Visible{% endif %}", {"show": True}, "Visible"),
            ("{% if show %}Visible{% endif %}", {"show": False}, ""),
        ],
        ids=["if_true", "if_false"],
    )
    def test_simple_if(self, template: str, context: dict, expected: str) -> None:
        """Test simple if block."""
        result = render_template(template, context)
        assert result == expected

    def test_if_else(self) -> None:
        """Test if/else block."""
        template = "{% if is_admin %}Admin{% else %}User{% endif %}"
        assert render_template(template, {"is_admin": True}) == "Admin"
        assert render_template(template, {"is_admin": False}) == "User"

    @pytest.mark.parametrize(
        "role,expected",
        [
            ("admin", "Admin"),
            ("moderator", "Mod"),
            ("guest", "User"),
        ],
        ids=["admin", "moderator", "guest"],
    )
    def test_if_elif_else(self, role: str, expected: str) -> None:
        """Test if/elif/else block."""
        template = '{% if role == "admin" %}Admin{% elif role == "moderator" %}Mod{% else %}User{% endif %}'
        result = render_template(template, {"role": role})
        assert result == expected

    @pytest.mark.parametrize(
        "outer,inner,expected",
        [
            (True, True, "Both"),
            (True, False, ""),
            (False, True, ""),
        ],
        ids=["both_true", "outer_only", "inner_only"],
    )
    def test_nested_if(self, outer: bool, inner: bool, expected: str) -> None:
        """Test nested if blocks."""
        template = "{% if outer %}{% if inner %}Both{% endif %}{% endif %}"
        result = render_template(template, {"outer": outer, "inner": inner})
        assert result == expected

    def test_if_with_variable(self) -> None:
        """Test if block containing variables."""
        template = "{% if user %}Hello {{ user.name }}!{% endif %}"
        result = render_template(template, {"user": {"name": "John"}})
        assert result == "Hello John!"

    @pytest.mark.parametrize(
        "status,expected",
        [
            ("active", "Active"),
            ("pending", "Inactive"),
        ],
        ids=["active", "pending"],
    )
    def test_equality_comparison(self, status: str, expected: str) -> None:
        """Test equality comparison in condition."""
        template = '{% if status == "active" %}Active{% else %}Inactive{% endif %}'
        result = render_template(template, {"status": status})
        assert result == expected

    @pytest.mark.parametrize(
        "role,expected",
        [
            ("admin", "Authorized"),
            ("guest", ""),
        ],
        ids=["admin", "guest"],
    )
    def test_inequality_comparison(self, role: str, expected: str) -> None:
        """Test inequality comparison in condition."""
        template = '{% if role != "guest" %}Authorized{% endif %}'
        result = render_template(template, {"role": role})
        assert result == expected


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.mark.parametrize(
        "template,context,expected",
        [
            ("", {}, ""),
            ("Plain text", {}, "Plain text"),
            (
                "Use {{ braces }} for variables",
                {"braces": "double"},
                "Use double for variables",
            ),
            ("Value: {{ missing }}", {}, "Value: "),
            ("Count: {{ count }}", {"count": 42}, "Count: 42"),
            ("Active: {{ active }}", {"active": True}, "Active: True"),
        ],
        ids=[
            "empty_template",
            "no_variables",
            "variable_substitution",
            "missing_variable",
            "numeric_value",
            "boolean_value",
        ],
    )
    def test_edge_case(self, template: str, context: dict, expected: str) -> None:
        """Test edge cases."""
        result = render_template(template, context)
        assert result == expected


class TestSyntaxErrors:
    """Tests for syntax error detection."""

    @pytest.mark.parametrize(
        "template,context,error_fragment",
        [
            ("{% if x %}test", {"x": True}, "Unclosed"),
            (
                "{% for item in items %}{{ item }}{% endfor %}",
                {"items": []},
                "for",
            ),
            ("{% macro test() %}{% endmacro %}", {}, "macro"),
            ("{% if %}test{% endif %}", {}, "condition"),
            ("{% endif %}", {}, "Unexpected"),
        ],
        ids=[
            "unclosed_if",
            "for_loop_rejected",
            "macro_rejected",
            "if_without_condition",
            "stray_endif",
        ],
    )
    def test_syntax_error(self, template: str, context: dict, error_fragment: str) -> None:
        """Test syntax error detection."""
        with pytest.raises(TemplateSyntaxError) as exc_info:
            render_template(template, context)
        assert error_fragment.lower() in str(exc_info.value).lower() or (
            "not supported" in str(exc_info.value).lower()
        )


class TestValidation:
    """Tests for template validation."""

    @pytest.mark.parametrize(
        "template,should_have_errors",
        [
            ("Hello {{ name }}!", False),
            ("{% if x %}unclosed", True),
            ("{% for x in y %}{% endfor %}", True),
        ],
        ids=["valid", "unclosed_if", "for_loop"],
    )
    def test_validation(self, template: str, should_have_errors: bool) -> None:
        """Test template validation."""
        errors = validate_template(template)
        if should_have_errors:
            assert len(errors) > 0
        else:
            assert errors == []


class TestVariableExtraction:
    """Tests for variable extraction."""

    @pytest.mark.parametrize(
        "template,expected_variables",
        [
            ("Hello {{ name }}!", ["name"]),
            ("{{ user.email }}", ["user.email"]),
            ("{{ a }} and {{ b }} and {{ c }}", ["a", "b", "c"]),
            (
                "{% if user.active %}{{ user.name }}{% endif %}",
                ["user.active", "user.name"],
            ),
        ],
        ids=["simple", "dotted_path", "multiple", "from_condition"],
    )
    def test_extract_variables(self, template: str, expected_variables: list[str]) -> None:
        """Test variable extraction."""
        variables = extract_variables(template)
        for var in expected_variables:
            assert var in variables

    def test_no_duplicates(self) -> None:
        """Test no duplicate variables extracted."""
        variables = extract_variables("{{ name }} {{ name }} {{ name }}")
        assert variables.count("name") == 1


class TestRealWorldTemplates:
    """Tests with realistic email templates."""

    def test_welcome_email(self) -> None:
        """Test realistic welcome email template."""
        template = """Hello {{ user.name }},

Welcome to {{ app.name }}! Your account has been created successfully.

{% if user.is_trial %}Your free trial will expire in {{ trial.days_remaining }} days.{% endif %}

Best regards,
The {{ app.name }} Team"""

        context = {
            "user": {"name": "John", "is_trial": True},
            "app": {"name": "MyApp"},
            "trial": {"days_remaining": 14},
        }

        result = render_template(template, context)
        assert "Hello John" in result
        assert "Welcome to MyApp" in result
        assert "free trial will expire in 14 days" in result

    def test_order_confirmation(self) -> None:
        """Test realistic order confirmation template."""
        template = """Order #{{ order.number }} Confirmation

Dear {{ customer.name }},

Thank you for your order!

{% if order.is_gift %}This order will be shipped as a gift.{% endif %}

Shipping to: {{ customer.address.city }}

{% if customer.is_premium %}As a premium member, you get free shipping!{% else %}Standard shipping rates apply.{% endif %}"""

        context = {
            "order": {"number": "ORD-001", "is_gift": False},
            "customer": {
                "name": "Jane",
                "address": {"city": "New York"},
                "is_premium": True,
            },
        }

        result = render_template(template, context)
        assert "Order #ORD-001" in result
        assert "Dear Jane" in result
        assert "New York" in result
        assert "free shipping" in result
        assert "gift" not in result.lower()
