"""
Wiring tests for the compliance pipeline (#839).

Pins the fact that citation/renderer/slicer are now called from the CLI
and MCP runtime paths. Previously the three modules had zero importers in
src/ — only tests imported them — and cycle 369 filed that as an orphan
cluster. These tests fail if the wiring is removed.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

CLI_FILE = Path(__file__).resolve().parents[2] / "src" / "dazzle" / "cli" / "compliance.py"
MCP_FILE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "mcp"
    / "server"
    / "handlers"
    / "compliance_handler.py"
)


class TestCliWiring:
    """The CLI must import the three formerly-orphan modules."""

    def test_cli_imports_slicer(self) -> None:
        assert "from dazzle.compliance.slicer import slice_auditspec" in CLI_FILE.read_text()

    def test_cli_imports_renderer(self) -> None:
        assert "from dazzle.compliance.renderer import" in CLI_FILE.read_text()

    def test_cli_imports_citation(self) -> None:
        assert "from dazzle.compliance.citation import validate_citations" in CLI_FILE.read_text()

    def test_cli_exposes_render_subcommand(self) -> None:
        from dazzle.cli.compliance import compliance_app

        runner = CliRunner()
        result = runner.invoke(compliance_app, ["--help"])
        assert result.exit_code == 0
        assert "render" in result.stdout
        assert "validate-citations" in result.stdout

    def test_render_without_deps_prints_install_hint(self, tmp_path: Path) -> None:
        """When weasyprint is missing, render exits 1 with a clear message."""
        # Simulate missing deps by monkey-patching HAS_RENDERER_DEPS.
        import dazzle.compliance.renderer as renderer_mod
        from dazzle.cli.compliance import compliance_app

        original = renderer_mod.HAS_RENDERER_DEPS
        renderer_mod.HAS_RENDERER_DEPS = False
        try:
            md = tmp_path / "doc.md"
            md.write_text("# Title\n")
            out = tmp_path / "doc.pdf"
            runner = CliRunner()
            result = runner.invoke(
                compliance_app,
                ["render", str(md), "--output", str(out)],
            )
            assert result.exit_code == 1
            assert "PDF rendering requires optional dependencies" in result.stdout
        finally:
            renderer_mod.HAS_RENDERER_DEPS = original


class TestMcpHandlerWiring:
    """The MCP handler must use slicer instead of an inline filter."""

    def test_handler_imports_slicer(self) -> None:
        assert "from dazzle.compliance.slicer import slice_auditspec" in MCP_FILE.read_text()

    def test_gaps_handler_accepts_filter_args(self) -> None:
        """The wired signature accepts status_filter + tier_filter args."""
        from dazzle.compliance.slicer import slice_auditspec

        fixture = {
            "controls": [
                {
                    "control_id": "A.1",
                    "control_name": "Example",
                    "status": "gap",
                    "tier": 1,
                },
                {
                    "control_id": "A.2",
                    "control_name": "Example2",
                    "status": "evidenced",
                    "tier": 2,
                },
                {
                    "control_id": "A.3",
                    "control_name": "Example3",
                    "status": "partial",
                    "tier": 2,
                },
            ],
        }
        # status_filter default
        sliced = slice_auditspec(fixture, status_filter=["gap", "partial"])
        assert len(sliced["controls"]) == 2

        # tier_filter narrowing
        sliced = slice_auditspec(fixture, status_filter=["gap", "partial"], tier_filter=[2])
        assert len(sliced["controls"]) == 1
        assert sliced["controls"][0]["control_id"] == "A.3"
