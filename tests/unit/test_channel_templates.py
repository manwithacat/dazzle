"""
Unit tests for DAZZLE messaging template engine (v0.9.0).

Tests the restricted Jinja-ish template syntax.
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

    def test_simple_variable(self):
        """Test simple variable interpolation."""
        result = render_template("Hello {{ name }}!", {"name": "World"})
        assert result == "Hello World!"

    def test_dotted_path(self):
        """Test dotted path variable access."""
        result = render_template(
            "Hello {{ user.name }}!",
            {"user": {"name": "John"}},
        )
        assert result == "Hello John!"

    def test_deep_nesting(self):
        """Test deeply nested variable access."""
        result = render_template(
            "Order: {{ order.customer.address.city }}",
            {"order": {"customer": {"address": {"city": "London"}}}},
        )
        assert result == "Order: London"

    def test_missing_variable_empty_string(self):
        """Test that missing variables render as empty string."""
        result = render_template("Hello {{ name }}!", {})
        assert result == "Hello !"

    def test_none_value_empty_string(self):
        """Test that None values render as empty string."""
        result = render_template("Value: {{ value }}", {"value": None})
        assert result == "Value: "

    def test_multiple_variables(self):
        """Test multiple variable interpolations."""
        result = render_template(
            "{{ greeting }}, {{ name }}! Your order #{{ order_num }} is ready.",
            {"greeting": "Hello", "name": "John", "order_num": "1234"},
        )
        assert result == "Hello, John! Your order #1234 is ready."

    def test_variable_with_whitespace(self):
        """Test variable with whitespace in braces."""
        result = render_template("{{  name  }}", {"name": "Test"})
        assert result == "Test"


class TestConditionals:
    """Tests for conditional blocks."""

    def test_simple_if_true(self):
        """Test simple if block when true."""
        result = render_template(
            "{% if show %}Visible{% endif %}",
            {"show": True},
        )
        assert result == "Visible"

    def test_simple_if_false(self):
        """Test simple if block when false."""
        result = render_template(
            "{% if show %}Visible{% endif %}",
            {"show": False},
        )
        assert result == ""

    def test_if_else(self):
        """Test if/else block."""
        template = "{% if is_admin %}Admin{% else %}User{% endif %}"

        result_admin = render_template(template, {"is_admin": True})
        assert result_admin == "Admin"

        result_user = render_template(template, {"is_admin": False})
        assert result_user == "User"

    def test_if_elif_else(self):
        """Test if/elif/else block."""
        template = """{% if role == "admin" %}Admin{% elif role == "moderator" %}Mod{% else %}User{% endif %}"""

        assert render_template(template, {"role": "admin"}) == "Admin"
        assert render_template(template, {"role": "moderator"}) == "Mod"
        assert render_template(template, {"role": "guest"}) == "User"

    def test_nested_if(self):
        """Test nested if blocks."""
        template = """{% if outer %}{% if inner %}Both{% endif %}{% endif %}"""

        assert render_template(template, {"outer": True, "inner": True}) == "Both"
        assert render_template(template, {"outer": True, "inner": False}) == ""
        assert render_template(template, {"outer": False, "inner": True}) == ""

    def test_if_with_variable(self):
        """Test if block containing variables."""
        template = "{% if user %}Hello {{ user.name }}!{% endif %}"

        result = render_template(template, {"user": {"name": "John"}})
        assert result == "Hello John!"

    def test_equality_comparison(self):
        """Test equality comparison in condition."""
        template = '{% if status == "active" %}Active{% else %}Inactive{% endif %}'

        assert render_template(template, {"status": "active"}) == "Active"
        assert render_template(template, {"status": "pending"}) == "Inactive"

    def test_inequality_comparison(self):
        """Test inequality comparison in condition."""
        template = '{% if role != "guest" %}Authorized{% endif %}'

        assert render_template(template, {"role": "admin"}) == "Authorized"
        assert render_template(template, {"role": "guest"}) == ""


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_empty_template(self):
        """Test empty template."""
        result = render_template("", {})
        assert result == ""

    def test_no_variables(self):
        """Test template with no variables."""
        result = render_template("Plain text", {})
        assert result == "Plain text"

    def test_double_braces_interpreted_as_variables(self):
        """Test that double braces are always interpreted as variables."""
        # Valid variable syntax should work
        result = render_template("Use {{ braces }} for variables", {"braces": "double"})
        assert result == "Use double for variables"

        # Missing variables render as empty string (not an error)
        result = render_template("Value: {{ missing }}", {})
        assert result == "Value: "

    def test_numeric_value(self):
        """Test numeric values."""
        result = render_template("Count: {{ count }}", {"count": 42})
        assert result == "Count: 42"

    def test_boolean_value(self):
        """Test boolean values."""
        result = render_template("Active: {{ active }}", {"active": True})
        assert result == "Active: True"


class TestSyntaxErrors:
    """Tests for syntax error detection."""

    def test_unclosed_if(self):
        """Test unclosed if block raises error."""
        with pytest.raises(TemplateSyntaxError) as exc_info:
            render_template("{% if x %}test", {"x": True})
        assert "Unclosed" in str(exc_info.value)

    def test_for_loop_rejected(self):
        """Test that for loops are rejected."""
        with pytest.raises(TemplateSyntaxError) as exc_info:
            render_template("{% for item in items %}{{ item }}{% endfor %}", {"items": []})
        assert (
            "for" in str(exc_info.value).lower() or "not supported" in str(exc_info.value).lower()
        )

    def test_macro_rejected(self):
        """Test that macros are rejected."""
        with pytest.raises(TemplateSyntaxError) as exc_info:
            render_template("{% macro test() %}{% endmacro %}", {})
        assert (
            "macro" in str(exc_info.value).lower() or "not supported" in str(exc_info.value).lower()
        )

    def test_if_without_condition(self):
        """Test if without condition raises error."""
        with pytest.raises(TemplateSyntaxError) as exc_info:
            render_template("{% if %}test{% endif %}", {})
        assert "condition" in str(exc_info.value).lower()

    def test_stray_endif(self):
        """Test stray endif raises error."""
        with pytest.raises(TemplateSyntaxError) as exc_info:
            render_template("{% endif %}", {})
        assert "Unexpected" in str(exc_info.value)


class TestValidation:
    """Tests for template validation."""

    def test_valid_template(self):
        """Test validation of valid template."""
        errors = validate_template("Hello {{ name }}!")
        assert errors == []

    def test_invalid_template(self):
        """Test validation catches errors."""
        errors = validate_template("{% if x %}unclosed")
        assert len(errors) > 0

    def test_validation_for_loop(self):
        """Test validation catches for loops."""
        errors = validate_template("{% for x in y %}{% endfor %}")
        assert len(errors) > 0


class TestVariableExtraction:
    """Tests for variable extraction."""

    def test_extract_simple_variable(self):
        """Test extracting simple variable."""
        variables = extract_variables("Hello {{ name }}!")
        assert "name" in variables

    def test_extract_dotted_path(self):
        """Test extracting dotted path."""
        variables = extract_variables("{{ user.email }}")
        assert "user.email" in variables

    def test_extract_multiple_variables(self):
        """Test extracting multiple variables."""
        variables = extract_variables("{{ a }} and {{ b }} and {{ c }}")
        assert "a" in variables
        assert "b" in variables
        assert "c" in variables

    def test_extract_from_condition(self):
        """Test extracting variables from conditions."""
        variables = extract_variables("{% if user.active %}{{ user.name }}{% endif %}")
        assert "user.active" in variables
        assert "user.name" in variables

    def test_no_duplicates(self):
        """Test no duplicate variables extracted."""
        variables = extract_variables("{{ name }} {{ name }} {{ name }}")
        assert variables.count("name") == 1


class TestRealWorldTemplates:
    """Tests with realistic email templates."""

    def test_welcome_email(self):
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

    def test_order_confirmation(self):
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
