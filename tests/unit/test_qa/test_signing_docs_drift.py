"""Drift gate: persona-tool catalogue + report schema must match the docs."""

from pathlib import Path

from dazzle.qa.signing_tools import build_signing_tools

DOCS = Path(__file__).resolve().parents[3] / "docs" / "reference" / "document-signing.md"


def test_docs_list_all_persona_tools():
    tools = build_signing_tools(
        base_url="x",
        inbox_path=Path("/tmp/i.json"),
        seeded_docs=[],
        action_sink={},
    )
    docs_text = DOCS.read_text()
    for tool in tools:
        assert f"`{tool.name}`" in docs_text, (
            f"docs must mention persona tool `{tool.name}` in the QA trial harness section"
        )


def test_docs_include_signing_outcomes_keys():
    docs_text = DOCS.read_text()
    for key in [
        "detected",
        "expected_outcome_inferred",
        "functional",
        "signature_integrity",
        "latency_ms",
    ]:
        assert key in docs_text, f"docs must document signing_outcomes key `{key}`"
