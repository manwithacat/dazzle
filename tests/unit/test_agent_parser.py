"""Tests for the DazzleAgent text-protocol parser and bracket counter helper.

Covers:
- _extract_first_json_object bracket counter (9 tests)
- _parse_action three-tier fallback (14 tests, added in task 2)
- Cycle 147 prose-before-JSON regression (1 test, added in task 3)
"""

from dazzle.agent.core import _extract_first_json_object


class TestBracketCounter:
    """Unit tests for _extract_first_json_object.

    The helper scans a string for the first balanced JSON object, respecting
    string literals and escape sequences. It returns (json_substring, surrounding_text)
    where surrounding_text is everything in the input minus the extracted object.
    If no balanced object is found, returns (None, original_text).
    """

    def test_extract_simple_object(self) -> None:
        json_str, surrounding = _extract_first_json_object('{"a": 1}')
        assert json_str == '{"a": 1}'
        assert surrounding == ""

    def test_extract_with_prose_before(self) -> None:
        json_str, surrounding = _extract_first_json_object('hello {"a": 1}')
        assert json_str == '{"a": 1}'
        assert surrounding == "hello "

    def test_extract_with_prose_after(self) -> None:
        json_str, surrounding = _extract_first_json_object('{"a": 1} world')
        assert json_str == '{"a": 1}'
        assert surrounding == " world"

    def test_extract_with_prose_around(self) -> None:
        json_str, surrounding = _extract_first_json_object('before {"a": 1} after')
        assert json_str == '{"a": 1}'
        assert surrounding == "before  after"

    def test_extract_nested(self) -> None:
        json_str, surrounding = _extract_first_json_object('{"a": {"b": 1}}')
        assert json_str == '{"a": {"b": 1}}'
        assert surrounding == ""

    def test_extract_with_brace_in_string(self) -> None:
        """Braces inside string literals must not be counted as structural brackets."""
        json_str, surrounding = _extract_first_json_object('{"a": "hello {world}"}')
        assert json_str == '{"a": "hello {world}"}'
        assert surrounding == ""

    def test_extract_with_escaped_quote(self) -> None:
        """Backslash-escaped quotes inside string literals must not close the string."""
        json_str, surrounding = _extract_first_json_object('{"a": "she said \\"hi\\""}')
        assert json_str == '{"a": "she said \\"hi\\""}'
        assert surrounding == ""

    def test_extract_multiple_objects_takes_first(self) -> None:
        json_str, surrounding = _extract_first_json_object('{"a": 1} {"b": 2}')
        assert json_str == '{"a": 1}'
        assert surrounding == ' {"b": 2}'

    def test_extract_no_object(self) -> None:
        json_str, surrounding = _extract_first_json_object("no braces here")
        assert json_str is None
        assert surrounding == "no braces here"

    def test_extract_unbalanced(self) -> None:
        """Missing closing brace — no balanced object found."""
        json_str, surrounding = _extract_first_json_object('{"a": 1')
        assert json_str is None
        assert surrounding == '{"a": 1'
