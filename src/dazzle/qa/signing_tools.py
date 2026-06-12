"""Five persona-facing tools for driving the signing flow in `dazzle qa trial`.

Exported public function: :func:`build_signing_tools`.

Each tool:
- Records its name in ``action_sink["invoked"]`` on entry.
- Appends HTTP call records to ``action_sink["requests"]``.
- Returns a short string describing the outcome — no exception escapes the tool boundary.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from dazzle.agent.core import AgentTool
from dazzle.qa.signing_seed import SeededDoc

# Minimal valid 10×10 white PNG (base64, no data-URL prefix).
# A 1×1 minimal PNG passes PIL but is rejected by fpdf2's own PNG parser
# ("broken data stream").  The 10×10 PIL-generated PNG is accepted by both.
# Used as a stub signature image for the signing route's `signature_png_b64` field.
_STUB_SIGNATURE_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAIAAAACUFjqAAAAFklEQVR4nGP8//8/A27AhEeOYeRKAwCl4wMRx3ocVQAAAABJRU5ErkJggg=="

# open_signing_link page-text cap. The signing document is the payload the
# persona must read to make a signing decision — generous on purpose (#1378).
_PAGE_TEXT_CAP = 4000


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

        lines = [f"Signing inbox ({len(entries)} pending):", ""]
        for i, entry in enumerate(entries, start=1):
            entity = entry.get("entity", "?")
            doc_id = entry.get("id", "?")
            token = entry.get("token", "?")
            email = entry.get("signatory_email", "")
            lines.append(f"[{i}] entity: {entity}")
            lines.append(f"    id: {doc_id}")
            lines.append(f"    token: {token}")
            lines.append(f"    signatory_email: {email}")
            lines.append("")
        return "\n".join(lines)

    return AgentTool(
        name="read_inbox",
        description=(
            "Read the signing inbox and return all pending signing requests. "
            "Each entry shows the entity, id, and token on separate lines — "
            "copy them VERBATIM into open_signing_link. "
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
        if matched is None:
            available = ", ".join(f"{d.entity}/{d.id}" for d in seeded_docs)
            return (
                f"No inbox entry matched entity={entity!r}, id={id!r}. "
                f"Re-read the inbox; available documents: {available}. "
                f"Pass entity, id, and token EXACTLY as shown."
            )

        action_sink["active_doc"] = matched

        url = f"{base_url}/sign/{entity}/{id}?token={token}"
        try:
            resp = httpx.get(url, timeout=10.0)
            _record_request(action_sink, method="GET", url=url, status=resp.status_code)
            # Strip HTML tags and collapse whitespace to give the LLM readable text.
            page_text = re.sub(r"<[^>]+>", " ", resp.text)
            page_text = re.sub(r"\s+", " ", page_text).strip()
            # The document IS the payload on a signing page — a tight cap
            # cut legal terms mid-clause and personas filed false
            # "document truncated" bugs (#1378). Cap generously, and when
            # we do cut, say so explicitly so the persona never mistakes
            # the tool's excerpt for a broken document.
            if len(page_text) > _PAGE_TEXT_CAP:
                page_text = page_text[:_PAGE_TEXT_CAP] + (
                    " …[tool excerpt truncated — the full document continues on the "
                    "real page; do NOT report this cut-off as a product bug]"
                )
            return (
                f"Opened signing page for {entity}/{id}: "
                f"HTTP {resp.status_code} ({len(resp.content)} bytes).\n\n"
                f"Document content:\n{page_text}\n\n"
                "The signing page is now loaded. The document content above is what\n"
                "you would see in a browser. Do NOT call the navigate tool — the page\n"
                "is already open from your perspective.\n\n"
                "Your next step is one of:\n"
                "- sign_document(authority_confirmed=true) to accept and sign\n"
                '- decline_signing(reason="...") to refuse\n'
                "- tamper_token() (only if explicitly testing tamper-detection)\n"
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
        # SignSubmission body: token is required; signature_png_b64 is the stub
        # image; signatory_name defaults to the seeded email when omitted.
        payload = {
            "token": doc.token,
            "signature_png_b64": _STUB_SIGNATURE_PNG_B64,
            "signatory_name": doc.signatory_email,
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

        # Decline uses the same POST /api/sign/{entity}/{id} endpoint with
        # decline=True + decline_reason in the SignSubmission body.
        url = f"{base_url}/api/sign/{doc.entity}/{doc.id}"
        payload = {
            "token": doc.token,
            "decline": True,
            "decline_reason": reason,
        }
        try:
            resp = httpx.post(url, json=payload, timeout=10.0)
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
