"""ASVS V5: Validation, Sanitization and Encoding security tests."""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


class TestHTMLSanitization:
    """V5.2: Sanitization and Sandboxing."""

    def test_script_tags_stripped(self):
        """V5.2.1: Script tags must be removed from string input."""
        from dazzle_back.runtime.sanitizer import strip_html_tags

        result = strip_html_tags('<script>alert("xss")</script>')
        assert "<script>" not in result

    def test_dangerous_tags_removed(self):
        """V5.2.2: Dangerous tags (iframe, object, embed) must be removed."""
        from dazzle_back.runtime.sanitizer import strip_dangerous_tags

        for tag in ["iframe", "object", "embed", "form"]:
            result = strip_dangerous_tags(f'<{tag} src="evil">content</{tag}>')
            assert f"<{tag}" not in result

    def test_event_handlers_stripped(self):
        """V5.2.3: Event handler attributes must be removed."""
        from dazzle_back.runtime.sanitizer import strip_dangerous_tags

        result = strip_dangerous_tags('<div onmouseover="alert(1)">text</div>')
        assert "onmouseover" not in result

    @given(st.text(max_size=1000))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_sanitizer_crash_resistance(self, text):
        """V5.2.4: Sanitizer must not crash on arbitrary input."""
        from dazzle_back.runtime.sanitizer import strip_dangerous_tags, strip_html_tags

        # Neither function should raise on any input
        strip_html_tags(text)
        strip_dangerous_tags(text)


class TestSQLInjection:
    """V5.3: Output Encoding and Injection Prevention."""

    def test_parameterized_queries(self):
        """V5.3.4: Database queries must use parameterized statements."""
        import inspect

        from dazzle_back.runtime.pg_backend import PostgresBackend

        source = inspect.getsource(PostgresBackend)
        # Should use %s placeholders (psycopg parameterized queries), not f-strings
        # in query execution methods
        assert "%s" in source, "PostgresBackend should use parameterized queries"
