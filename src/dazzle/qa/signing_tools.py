"""Five persona-facing tools for driving the signing flow in `dazzle qa trial`.

Exported public function: :func:`build_signing_tools`.

Each tool:
- Records its name in ``action_sink["invoked"]`` on entry.
- Appends HTTP call records to ``action_sink["requests"]``.
- Returns a short string describing the outcome — no exception escapes the tool boundary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from dazzle.agent.core import AgentTool
from dazzle.qa.signing_seed import SeededDoc

# Synthetic PNG stub — 1×1 transparent pixel, base64-encoded PKCS header only.
_STUB_SIGNATURE = "data:image/png;base64,iVBORw0KGgo="


def build_signing_tools(
    *,
    base_url: str,
    inbox_path: Path,
    seeded_docs: list[SeededDoc],
    action_sink: dict[str, Any],
) -> list[AgentTool]:
    """Return the five persona-facing signing tools.

    Args:
        base_url: Root URL of the running Dazzle app (e.g. ``http://localhost:3000``).
        inbox_path: Path to the mock inbox JSON file written by :mod:`dazzle.qa.signing_seed`.
        seeded_docs: Pre-seeded :class:`~dazzle.qa.signing_seed.SeededDoc` objects so
            ``open_signing_link`` can match by entity/id.
        action_sink: Mutable dict shared across all tools.  Tools record
            ``sink["invoked"]``, ``sink["requests"]``, and ``sink["active_doc"]``.

    Returns:
        A list of five :class:`~dazzle.agent.core.AgentTool` instances.
    """
    return [
        _make_read_inbox(inbox_path=inbox_path, action_sink=action_sink),
        _make_open_signing_link(
            base_url=base_url, seeded_docs=seeded_docs, action_sink=action_sink
        ),
        _make_sign_document(base_url=base_url, action_sink=action_sink),
        _make_decline_signing(base_url=base_url, action_sink=action_sink),
        _make_tamper_token(base_url=base_url, action_sink=action_sink),
    ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _record_invocation(sink: dict[str, Any], name: str) -> None:
    sink.setdefault("invoked", []).append(name)


def _record_request(sink: dict[str, Any], *, method: str, url: str, status: int | str) -> None:
    sink.setdefault("requests", []).append({"method": method, "url": url, "status": status})


def _active_doc(sink: dict[str, Any]) -> SeededDoc | None:
    return sink.get("active_doc")


# ---------------------------------------------------------------------------
# Tool factories
# ---------------------------------------------------------------------------


def _make_read_inbox(*, inbox_path: Path, action_sink: dict[str, Any]) -> AgentTool:
    def read_inbox() -> str:
        _record_invocation(action_sink, "read_inbox")
        try:
            raw = inbox_path.read_text(encoding="utf-8")
            entries: list[dict[str, Any]] = json.loads(raw)
        except (FileNotFoundError, json.JSONDecodeError):
            entries = []

        if not isinstance(entries, list):
            return "Inbox is empty."

        if not entries:
            return "Inbox is empty."

        lines = ["Signing inbox:"]
        for i, entry in enumerate(entries, start=1):
            entity = entry.get("entity", "?")
            doc_id = entry.get("id", "?")
            url = entry.get("signing_url", "")
            email = entry.get("signatory_email", "")
            lines.append(f"  {i}. {entity}/{doc_id} — signatory: {email} — URL: {url}")
        return "\n".join(lines)

    return AgentTool(
        name="read_inbox",
        description=(
            "Read the signing inbox and return all pending signing requests. "
            "Call this first to discover which documents need to be signed."
        ),
        schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
        handler=read_inbox,
    )


def _make_open_signing_link(
    *,
    base_url: str,
    seeded_docs: list[SeededDoc],
    action_sink: dict[str, Any],
) -> AgentTool:
    def open_signing_link(entity: str, id: str, token: str) -> str:  # noqa: A002
        _record_invocation(action_sink, "open_signing_link")

        # Match against seeded docs so downstream tools know the active document.
        matched = next((d for d in seeded_docs if d.entity == entity and d.id == id), None)
        if matched is not None:
            action_sink["active_doc"] = matched

        url = f"{base_url}/sign/{entity}/{id}?token={token}"
        try:
            resp = httpx.get(url, timeout=10.0)
            _record_request(action_sink, method="GET", url=url, status=resp.status_code)
            return (
                f"Opened signing page for {entity}/{id}: "
                f"HTTP {resp.status_code} ({len(resp.content)} bytes)."
            )
        except httpx.HTTPError as exc:
            _record_request(action_sink, method="GET", url=url, status="error")
            return f"HTTP error opening {entity}/{id}: {exc}"

    return AgentTool(
        name="open_signing_link",
        description=(
            "Navigate to a signing link for a specific document. "
            "Use entity, id, and token from read_inbox output. "
            "This sets the active document for subsequent sign/decline/tamper calls."
        ),
        schema={
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "DSL entity name (e.g. EngagementLetter).",
                },
                "id": {
                    "type": "string",
                    "description": "Document ID (UUID string).",
                },
                "token": {
                    "type": "string",
                    "description": "HMAC signing token from the inbox entry.",
                },
            },
            "required": ["entity", "id", "token"],
        },
        handler=open_signing_link,
    )


def _make_sign_document(*, base_url: str, action_sink: dict[str, Any]) -> AgentTool:
    def sign_document(authority_confirmed: bool) -> str:
        _record_invocation(action_sink, "sign_document")

        if not authority_confirmed:
            return (
                "Signing refused: you must set authority_confirmed=true to confirm "
                "you have authority to sign on behalf of the signatory."
            )

        doc = _active_doc(action_sink)
        if doc is None:
            return (
                "Error: no active document. Call open_signing_link first to select "
                "a document from the inbox."
            )

        url = f"{base_url}/api/sign/{doc.entity}/{doc.id}"
        payload = {
            "signature_data_url": _STUB_SIGNATURE,
            "authority_confirmed": True,
        }
        try:
            resp = httpx.post(url, json=payload, timeout=30.0)
            _record_request(action_sink, method="POST", url=url, status=resp.status_code)
            return f"Signed {doc.entity}/{doc.id}: HTTP {resp.status_code}. Body: {resp.text[:200]}"
        except httpx.HTTPError as exc:
            _record_request(action_sink, method="POST", url=url, status="error")
            return f"HTTP error signing {doc.entity}/{doc.id}: {exc}"

    return AgentTool(
        name="sign_document",
        description=(
            "Submit a signature for the active document. "
            "You must have called open_signing_link first. "
            "Set authority_confirmed=true only if you genuinely have signing authority."
        ),
        schema={
            "type": "object",
            "properties": {
                "authority_confirmed": {
                    "type": "boolean",
                    "description": (
                        "Confirm you have authority to sign. "
                        "Must be true to proceed; set false to abort without signing."
                    ),
                },
            },
            "required": ["authority_confirmed"],
        },
        handler=sign_document,
    )


def _make_decline_signing(*, base_url: str, action_sink: dict[str, Any]) -> AgentTool:
    def decline_signing(reason: str) -> str:
        _record_invocation(action_sink, "decline_signing")

        doc = _active_doc(action_sink)
        if doc is None:
            return (
                "Error: no active document. Call open_signing_link first to select "
                "a document from the inbox."
            )

        url = f"{base_url}/api/sign/{doc.entity}/{doc.id}/decline"
        try:
            resp = httpx.post(url, json={"reason": reason}, timeout=10.0)
            _record_request(action_sink, method="POST", url=url, status=resp.status_code)
            return (
                f"Declined {doc.entity}/{doc.id}: HTTP {resp.status_code}. "
                f"Reason recorded: {reason!r}."
            )
        except httpx.HTTPError as exc:
            _record_request(action_sink, method="POST", url=url, status="error")
            return f"HTTP error declining {doc.entity}/{doc.id}: {exc}"

    return AgentTool(
        name="decline_signing",
        description=(
            "Decline to sign the active document, recording a reason. "
            "You must have called open_signing_link first."
        ),
        schema={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Human-readable reason for declining (1-3 sentences).",
                },
            },
            "required": ["reason"],
        },
        handler=decline_signing,
    )


def _make_tamper_token(*, base_url: str, action_sink: dict[str, Any]) -> AgentTool:
    def tamper_token() -> str:
        _record_invocation(action_sink, "tamper_token")

        doc = _active_doc(action_sink)
        if doc is None:
            return (
                "Error: no active document. Call open_signing_link first to select "
                "a document from the inbox."
            )

        bad_token = doc.token[:-4] + "ZZZZ" if len(doc.token) >= 4 else doc.token + "ZZZZ"
        url = f"{base_url}/sign/{doc.entity}/{doc.id}?token={bad_token}"
        try:
            resp = httpx.get(url, timeout=10.0)
            _record_request(action_sink, method="GET", url=url, status=resp.status_code)
            return (
                f"Tamper test for {doc.entity}/{doc.id} with bad token "
                f"{bad_token!r}: HTTP {resp.status_code}. "
                f"Expected 400/401/403/404; got {resp.status_code}."
            )
        except httpx.HTTPError as exc:
            _record_request(action_sink, method="GET", url=url, status="error")
            return f"HTTP error during tamper test for {doc.entity}/{doc.id}: {exc}"

    return AgentTool(
        name="tamper_token",
        description=(
            "Test the signing link with a deliberately corrupted token to verify "
            "the server rejects tampered requests. "
            "You must have called open_signing_link first."
        ),
        schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
        handler=tamper_token,
    )
