"""Tests for dazzle.qa.signing_tools — five persona-facing signing tools."""

from pathlib import Path

from dazzle.agent.core import AgentTool
from dazzle.qa.signing_seed import SeededDoc
from dazzle.qa.signing_tools import build_signing_tools


def _invoke(tool: AgentTool, args: dict) -> str:
    """Call the tool with args and return its string result.

    Adapter that hides whether AgentTool uses .execute, .handler, or
    a different attribute. The test cares about the user-visible result
    string, not the calling convention.
    """
    for attr in ("execute", "handler", "call"):
        fn = getattr(tool, attr, None)
        if callable(fn):
            return fn(**args)
    raise AttributeError(f"Cannot invoke {tool}: no execute/handler/call attribute")


def test_returns_five_named_tools(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox.json"
    inbox.write_text("[]")
    tools = build_signing_tools(
        base_url="http://localhost:3000",
        inbox_path=inbox,
        seeded_docs=[],
        action_sink={},
    )
    names = {t.name for t in tools}
    assert names == {
        "read_inbox",
        "open_signing_link",
        "sign_document",
        "decline_signing",
        "tamper_token",
    }
    for tool in tools:
        assert isinstance(tool, AgentTool)


def test_read_inbox_returns_seeded_docs(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox.json"
    inbox.write_text(
        '[{"entity":"TestDoc","id":"abc","token":"tok",'
        '"signing_url":"http://x","signatory_email":"a@b.com"}]'
    )
    sink: dict = {}
    tools = build_signing_tools(
        base_url="http://localhost:3000",
        inbox_path=inbox,
        seeded_docs=[],
        action_sink=sink,
    )
    read_inbox = next(t for t in tools if t.name == "read_inbox")
    result = _invoke(read_inbox, {})
    assert "TestDoc" in result
    assert "abc" in result
    assert sink["invoked"] == ["read_inbox"]


def test_read_inbox_missing_file(tmp_path: Path) -> None:
    inbox = tmp_path / "nonexistent.json"
    sink: dict = {}
    tools = build_signing_tools(
        base_url="http://localhost:3000",
        inbox_path=inbox,
        seeded_docs=[],
        action_sink=sink,
    )
    read_inbox = next(t for t in tools if t.name == "read_inbox")
    result = _invoke(read_inbox, {})
    assert "empty" in result.lower()
    assert sink["invoked"] == ["read_inbox"]


def test_read_inbox_empty_list(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox.json"
    inbox.write_text("[]")
    sink: dict = {}
    tools = build_signing_tools(
        base_url="http://localhost:3000",
        inbox_path=inbox,
        seeded_docs=[],
        action_sink=sink,
    )
    read_inbox = next(t for t in tools if t.name == "read_inbox")
    result = _invoke(read_inbox, {})
    assert "empty" in result.lower()


def test_read_inbox_handles_non_list_json(tmp_path: Path) -> None:
    """read_inbox should return 'empty' when JSON is valid but not a list."""
    inbox = tmp_path / "inbox.json"
    inbox.write_text("{}")  # valid JSON, but not a list
    sink: dict = {}
    tools = build_signing_tools(
        base_url="http://localhost:3000",
        inbox_path=inbox,
        seeded_docs=[],
        action_sink=sink,
    )
    read_inbox = next(t for t in tools if t.name == "read_inbox")
    # Should not raise TypeError
    result = _invoke(read_inbox, {})
    assert "empty" in result.lower()


def test_sign_document_no_active_doc(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox.json"
    inbox.write_text("[]")
    sink: dict = {}
    tools = build_signing_tools(
        base_url="http://localhost:3000",
        inbox_path=inbox,
        seeded_docs=[],
        action_sink=sink,
    )
    sign = next(t for t in tools if t.name == "sign_document")
    result = _invoke(sign, {"authority_confirmed": True})
    assert "error" in result.lower() or "no" in result.lower()


def test_sign_document_authority_not_confirmed(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox.json"
    inbox.write_text("[]")
    sink: dict = {}
    tools = build_signing_tools(
        base_url="http://localhost:3000",
        inbox_path=inbox,
        seeded_docs=[],
        action_sink=sink,
    )
    sign = next(t for t in tools if t.name == "sign_document")
    result = _invoke(sign, {"authority_confirmed": False})
    # Should refuse, not raise
    assert isinstance(result, str)
    assert len(result) > 0


def test_decline_signing_no_active_doc(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox.json"
    inbox.write_text("[]")
    sink: dict = {}
    tools = build_signing_tools(
        base_url="http://localhost:3000",
        inbox_path=inbox,
        seeded_docs=[],
        action_sink=sink,
    )
    decline = next(t for t in tools if t.name == "decline_signing")
    result = _invoke(decline, {"reason": "Not ready"})
    assert "error" in result.lower() or "no" in result.lower()


def test_tamper_token_no_active_doc(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox.json"
    inbox.write_text("[]")
    sink: dict = {}
    tools = build_signing_tools(
        base_url="http://localhost:3000",
        inbox_path=inbox,
        seeded_docs=[],
        action_sink=sink,
    )
    tamper = next(t for t in tools if t.name == "tamper_token")
    result = _invoke(tamper, {})
    assert "error" in result.lower() or "no" in result.lower()


def test_all_tools_record_invocation(tmp_path: Path) -> None:
    """Each tool appends its name to sink['invoked']."""
    inbox = tmp_path / "inbox.json"
    inbox.write_text("[]")
    sink: dict = {}
    tools = build_signing_tools(
        base_url="http://localhost:3000",
        inbox_path=inbox,
        seeded_docs=[],
        action_sink=sink,
    )
    by_name = {t.name: t for t in tools}

    _invoke(by_name["read_inbox"], {})
    _invoke(by_name["sign_document"], {"authority_confirmed": False})
    _invoke(by_name["decline_signing"], {"reason": "test"})
    _invoke(by_name["tamper_token"], {})

    assert "read_inbox" in sink["invoked"]
    assert "sign_document" in sink["invoked"]
    assert "decline_signing" in sink["invoked"]
    assert "tamper_token" in sink["invoked"]


def test_open_signing_link_matches_seeded_doc(tmp_path: Path) -> None:
    """open_signing_link sets active_doc when a matching SeededDoc is found."""
    inbox = tmp_path / "inbox.json"
    inbox.write_text("[]")
    doc = SeededDoc(
        entity="Contract",
        id="doc-1",
        token="mytoken",
        signing_url="http://localhost:3000/sign/Contract/doc-1?token=mytoken",
        signatory_email="signer@example.com",
    )
    sink: dict = {}
    tools = build_signing_tools(
        base_url="http://localhost:3000",
        inbox_path=inbox,
        seeded_docs=[doc],
        action_sink=sink,
    )
    open_link = next(t for t in tools if t.name == "open_signing_link")
    # We don't actually fire HTTP in unit tests — the tool wraps errors gracefully
    result = _invoke(open_link, {"entity": "Contract", "id": "doc-1", "token": "mytoken"})
    # active_doc should be set regardless of HTTP success/failure
    assert sink.get("active_doc") == doc
    assert isinstance(result, str)
    assert sink["invoked"][-1] == "open_signing_link"
