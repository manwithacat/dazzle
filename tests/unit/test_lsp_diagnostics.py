"""Tests for LSP diagnostics publishing (issue #232)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.errors import ErrorContext, LinkError, ParseError, ValidationError


class TestDiagnosticsFromError:
    """_diagnostics_from_error extracts LSP diagnostics from DazzleErrors."""

    def test_parse_error_with_context(self) -> None:
        from dazzle.lsp.server import _diagnostics_from_error

        ctx = ErrorContext(file=Path("/tmp/test.dsl"), line=10, column=5)
        err = ParseError("Unexpected token 'foo'", ctx)

        result = _diagnostics_from_error(err)
        uri = Path("/tmp/test.dsl").as_uri()
        assert uri in result
        diags = result[uri]
        assert len(diags) == 1
        assert diags[0].message == "Unexpected token 'foo'"
        # LSP is 0-indexed, our errors are 1-indexed
        assert diags[0].range.start.line == 9
        assert diags[0].range.start.character == 4

    def test_parse_error_severity_is_error(self) -> None:
        from lsprotocol.types import DiagnosticSeverity

        from dazzle.lsp.server import _diagnostics_from_error

        ctx = ErrorContext(file=Path("/tmp/test.dsl"), line=1, column=1)
        err = ParseError("bad syntax", ctx)

        result = _diagnostics_from_error(err)
        uri = Path("/tmp/test.dsl").as_uri()
        assert result[uri][0].severity == DiagnosticSeverity.Error

    def test_link_error_severity_is_warning(self) -> None:
        from lsprotocol.types import DiagnosticSeverity

        from dazzle.lsp.server import _diagnostics_from_error

        ctx = ErrorContext(file=Path("/tmp/test.dsl"), line=5, column=1)
        err = LinkError("Unknown entity ref 'Foo'", ctx)

        result = _diagnostics_from_error(err)
        uri = Path("/tmp/test.dsl").as_uri()
        assert result[uri][0].severity == DiagnosticSeverity.Warning

    def test_validation_error_severity_is_warning(self) -> None:
        from lsprotocol.types import DiagnosticSeverity

        from dazzle.lsp.server import _diagnostics_from_error

        ctx = ErrorContext(file=Path("/tmp/test.dsl"), line=3, column=1)
        err = ValidationError("Entity missing pk", ctx)

        result = _diagnostics_from_error(err)
        uri = Path("/tmp/test.dsl").as_uri()
        assert result[uri][0].severity == DiagnosticSeverity.Warning

    def test_error_without_context_uses_fallback(self) -> None:
        from dazzle.lsp.server import _diagnostics_from_error

        err = ParseError("Something failed")

        result = _diagnostics_from_error(err)
        assert "__fallback__" in result
        assert len(result["__fallback__"]) == 1
        assert result["__fallback__"][0].message == "Something failed"

    def test_error_line_col_zero_indexed(self) -> None:
        """Line 1, col 1 in our errors should map to 0,0 in LSP."""
        from dazzle.lsp.server import _diagnostics_from_error

        ctx = ErrorContext(file=Path("/tmp/test.dsl"), line=1, column=1)
        err = ParseError("first line error", ctx)

        result = _diagnostics_from_error(err)
        uri = Path("/tmp/test.dsl").as_uri()
        diag = result[uri][0]
        assert diag.range.start.line == 0
        assert diag.range.start.character == 0


class TestMakeDiagnostic:
    """_make_diagnostic creates well-formed LSP Diagnostic objects."""

    def test_default_severity(self) -> None:
        from lsprotocol.types import DiagnosticSeverity

        from dazzle.lsp.server import _make_diagnostic

        diag = _make_diagnostic("test error")
        assert diag.severity == DiagnosticSeverity.Error
        assert diag.source == "dazzle"
        assert diag.message == "test error"

    def test_custom_severity(self) -> None:
        from lsprotocol.types import DiagnosticSeverity

        from dazzle.lsp.server import _make_diagnostic

        diag = _make_diagnostic("info", severity=DiagnosticSeverity.Information)
        assert diag.severity == DiagnosticSeverity.Information

    def test_line_zero_clamped(self) -> None:
        from dazzle.lsp.server import _make_diagnostic

        diag = _make_diagnostic("msg", line=0, col=0)
        assert diag.range.start.line == 0
        assert diag.range.start.character == 0
