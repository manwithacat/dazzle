"""MCP multi-session state isolation (#1628).

Agent hosts (Grok, Claude Code) spawn a **new** stdio process per session and
never attach to an existing PID. A single exclusive lock on
``.dazzle/mcp.lock`` made the monorepo a machine-wide mutex.

Default: each MCP process gets its own state directory under
``.dazzle/mcp-sessions/<session_id>/`` (KG + activity + optional lock).
Set ``DAZZLE_MCP_SHARED=1`` to restore the legacy single-process shared KG +
exclusive lock (for operators who want one shared graph).

Optional: ``DAZZLE_MCP_SESSION_ID`` to pin a stable session directory.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

_ENV_SHARED = "DAZZLE_MCP_SHARED"
_ENV_SESSION = "DAZZLE_MCP_SESSION_ID"
_ENV_SKIP_LOCK = "DAZZLE_MCP_SKIP_LOCK"


def mcp_shared_mode() -> bool:
    """True when legacy single-instance shared KG is requested."""
    return os.environ.get(_ENV_SHARED, "").strip() in ("1", "true", "yes")


def ensure_mcp_session_id() -> str:
    """Return session id, generating and exporting one if needed (non-shared)."""
    if mcp_shared_mode():
        return "shared"
    existing = os.environ.get(_ENV_SESSION, "").strip()
    if existing:
        return existing
    sid = f"s{os.getpid()}-{uuid.uuid4().hex[:8]}"
    os.environ[_ENV_SESSION] = sid
    return sid


def mcp_state_dir(project_root: Path) -> Path:
    """Directory for this MCP process's KG / activity / lock."""
    root = project_root.resolve()
    dazzle = root / ".dazzle"
    if mcp_shared_mode():
        return dazzle
    sid = ensure_mcp_session_id()
    # Sanitize path segments
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)[:80]
    return dazzle / "mcp-sessions" / (safe or f"s{os.getpid()}")


def mcp_lock_path(project_root: Path) -> Path:
    return mcp_state_dir(project_root) / "mcp.lock"


def mcp_kg_db_path(project_root: Path) -> Path:
    return mcp_state_dir(project_root) / "knowledge_graph.db"


def mcp_activity_log_path(project_root: Path) -> Path:
    return mcp_state_dir(project_root) / "mcp-activity.log"


def exclusive_lock_required() -> bool:
    """Whether cross-process exclusive lock is enforced.

    Multi-session default: False (each process has its own state dir).
    Shared mode: True unless DAZZLE_MCP_SKIP_LOCK=1.
    """
    if os.environ.get(_ENV_SKIP_LOCK) == "1":
        return False
    return mcp_shared_mode()
