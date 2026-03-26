# Admin CLI Commands — Batch 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four admin CLI commands: flush-sessions, impersonate (with magic link), rotate-passwords, and dbshell.

**Architecture:** Thin CLI commands in `auth.py` wrapping existing AuthStore methods. One new primitive — magic links — for one-time login tokens. dbshell is a standalone top-level command shelling out to `psql`.

**Tech Stack:** Python 3.12+, Typer CLI, psycopg, Rich console, secrets module

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle_back/runtime/auth/store.py` | Modify | Add `delete_all_sessions()` to SessionStoreMixin |
| `src/dazzle_back/runtime/auth/magic_link.py` | Create | Magic link token creation + validation + table DDL |
| `src/dazzle/cli/auth.py` | Modify | Add flush-sessions, impersonate, rotate-passwords commands |
| `src/dazzle/cli/dbshell.py` | Create | Top-level dbshell command |
| `src/dazzle/cli/__init__.py` | Modify | Register dbshell |
| `tests/unit/test_flush_sessions.py` | Create | Tests for flush-sessions command |
| `tests/unit/test_impersonate.py` | Create | Tests for impersonate command + magic link |
| `tests/unit/test_rotate_passwords.py` | Create | Tests for rotate-passwords command |
| `tests/unit/test_dbshell.py` | Create | Tests for dbshell command |

---

### Task 1: `delete_all_sessions()` on AuthStore

**Files:**
- Modify: `src/dazzle_back/runtime/auth/store.py`
- Test: `tests/unit/test_flush_sessions.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_flush_sessions.py`:

```python
"""Tests for flush-sessions command (#695)."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

runner = CliRunner()


class TestDeleteAllSessions:
    """Test the delete_all_sessions() AuthStore method."""

    def test_delete_all_sessions_returns_count(self):
        """delete_all_sessions() calls DELETE FROM sessions and returns count."""
        from dazzle_back.runtime.auth.store import SessionStoreMixin

        mixin = SessionStoreMixin.__new__(SessionStoreMixin)
        mixin._execute_modify = MagicMock(return_value=5)

        result = mixin.delete_all_sessions()

        assert result == 5
        mixin._execute_modify.assert_called_once()
        sql = mixin._execute_modify.call_args[0][0]
        assert "DELETE FROM sessions" in sql
        # No WHERE clause — deletes everything
        assert "WHERE" not in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_flush_sessions.py::TestDeleteAllSessions -v`
Expected: FAIL with `AttributeError: type object 'SessionStoreMixin' has no attribute 'delete_all_sessions'`

- [ ] **Step 3: Implement `delete_all_sessions`**

Add to `src/dazzle_back/runtime/auth/store.py` in `SessionStoreMixin`, after `cleanup_expired_sessions()` (around line 571):

```python
    def delete_all_sessions(self) -> int:
        """Delete all sessions for all users. Returns count deleted."""
        return int(self._execute_modify("DELETE FROM sessions"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_flush_sessions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/auth/store.py tests/unit/test_flush_sessions.py
git commit -m "feat: add delete_all_sessions() to SessionStoreMixin (#695)"
```

---

### Task 2: `flush-sessions` CLI Command

**Files:**
- Modify: `src/dazzle/cli/auth.py`
- Modify: `tests/unit/test_flush_sessions.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_flush_sessions.py`:

```python
class TestFlushSessionsCommand:
    """Test the dazzle auth flush-sessions CLI command."""

    @patch("dazzle.cli.auth._get_auth_store")
    def test_flush_all_requires_yes(self, mock_store_fn):
        """Without --yes, the command should prompt for confirmation."""
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["flush-sessions"], input="n\n")
        assert result.exit_code != 0

    @patch("dazzle.cli.auth._get_auth_store")
    def test_flush_all_with_yes(self, mock_store_fn):
        """With --yes, deletes all sessions."""
        mock_store = MagicMock()
        mock_store.delete_all_sessions.return_value = 42
        mock_store_fn.return_value = mock_store

        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["flush-sessions", "--yes"])
        assert result.exit_code == 0
        assert "42" in result.output
        mock_store.delete_all_sessions.assert_called_once()

    @patch("dazzle.cli.auth._get_auth_store")
    def test_flush_expired(self, mock_store_fn):
        """--expired calls cleanup_expired_sessions."""
        mock_store = MagicMock()
        mock_store.cleanup_expired_sessions.return_value = 10
        mock_store_fn.return_value = mock_store

        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["flush-sessions", "--expired"])
        assert result.exit_code == 0
        assert "10" in result.output
        mock_store.cleanup_expired_sessions.assert_called_once()

    @patch("dazzle.cli.auth._get_auth_store")
    def test_flush_user(self, mock_store_fn):
        """--user EMAIL calls delete_user_sessions for that user."""
        mock_store = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-uuid-123"
        mock_store.get_user_by_email.return_value = mock_user
        mock_store.delete_user_sessions.return_value = 3
        mock_store_fn.return_value = mock_store

        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["flush-sessions", "--user", "test@example.com"])
        assert result.exit_code == 0
        assert "3" in result.output

    @patch("dazzle.cli.auth._get_auth_store")
    def test_flush_json_output(self, mock_store_fn):
        """--json outputs JSON format."""
        mock_store = MagicMock()
        mock_store.delete_all_sessions.return_value = 5
        mock_store_fn.return_value = mock_store

        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["flush-sessions", "--yes", "--json"])
        assert result.exit_code == 0
        assert '"deleted"' in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_flush_sessions.py::TestFlushSessionsCommand -v`
Expected: FAIL

- [ ] **Step 3: Implement flush-sessions command**

Add to `src/dazzle/cli/auth.py` after the `cleanup_sessions` command:

```python
@auth_app.command(name="flush-sessions")
def flush_sessions(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    expired: Annotated[bool, typer.Option("--expired", help="Only remove expired sessions")] = False,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Flush sessions for specific user (email or UUID)")] = None,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Flush sessions — all, expired only, or for a specific user."""
    store = _get_auth_store()

    if expired:
        deleted = store.cleanup_expired_sessions()
    elif user:
        resolved = _resolve_user(store, user)
        if not resolved:
            console.print(f"[red]User not found: {user}[/red]")
            raise typer.Exit(1)
        deleted = store.delete_user_sessions(resolved.id)
    else:
        if not yes:
            confirm = typer.confirm("Delete ALL sessions? Every user will be logged out.")
            if not confirm:
                raise typer.Abort()
        deleted = store.delete_all_sessions()

    if output_json:
        console.print_json(json.dumps({"deleted": deleted}))
    else:
        console.print(f"[green]Deleted {deleted} session(s).[/green]")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_flush_sessions.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/auth.py tests/unit/test_flush_sessions.py
git commit -m "feat: dazzle auth flush-sessions command (#695)"
```

---

### Task 3: Magic Link Primitive

**Files:**
- Create: `src/dazzle_back/runtime/auth/magic_link.py`
- Modify: `src/dazzle_back/runtime/auth/store.py` (add table to `_init_db`)
- Test: `tests/unit/test_magic_link.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_magic_link.py`:

```python
"""Tests for magic link token lifecycle (#695)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from dazzle_back.runtime.auth.magic_link import create_magic_link, validate_magic_link


class TestCreateMagicLink:
    def test_returns_url_safe_token(self):
        mock_store = MagicMock()
        token = create_magic_link(mock_store, user_id="user-1", ttl_seconds=300, created_by="cli")
        assert len(token) > 20
        assert all(c.isalnum() or c in "-_" for c in token)

    def test_stores_token_in_db(self):
        mock_store = MagicMock()
        token = create_magic_link(mock_store, user_id="user-1", ttl_seconds=300, created_by="test")
        mock_store._execute_modify.assert_called_once()
        sql = mock_store._execute_modify.call_args[0][0]
        assert "INSERT INTO magic_links" in sql


class TestValidateMagicLink:
    def test_valid_token_returns_user_id(self):
        mock_store = MagicMock()
        future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        mock_store._execute.return_value = [
            {"user_id": "user-1", "expires_at": future, "used_at": None}
        ]
        result = validate_magic_link(mock_store, "some-token")
        assert result == "user-1"

    def test_expired_token_returns_none(self):
        mock_store = MagicMock()
        past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        mock_store._execute.return_value = [
            {"user_id": "user-1", "expires_at": past, "used_at": None}
        ]
        result = validate_magic_link(mock_store, "expired-token")
        assert result is None

    def test_used_token_returns_none(self):
        mock_store = MagicMock()
        future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        mock_store._execute.return_value = [
            {"user_id": "user-1", "expires_at": future, "used_at": "2026-03-26T12:00:00"}
        ]
        result = validate_magic_link(mock_store, "used-token")
        assert result is None

    def test_unknown_token_returns_none(self):
        mock_store = MagicMock()
        mock_store._execute.return_value = []
        result = validate_magic_link(mock_store, "unknown-token")
        assert result is None

    def test_marks_token_as_used(self):
        mock_store = MagicMock()
        future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        mock_store._execute.return_value = [
            {"user_id": "user-1", "expires_at": future, "used_at": None}
        ]
        validate_magic_link(mock_store, "some-token")
        # Should have called _execute_modify to mark used_at
        mock_store._execute_modify.assert_called_once()
        sql = mock_store._execute_modify.call_args[0][0]
        assert "UPDATE magic_links" in sql
        assert "used_at" in sql
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_magic_link.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement magic_link.py**

Create `src/dazzle_back/runtime/auth/magic_link.py`:

```python
"""Magic link tokens for one-time authentication.

Reusable primitive for CLI impersonation, passwordless email login,
and API-driven session creation.
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

# DDL for the magic_links table — called from AuthStore._init_db()
MAGIC_LINKS_DDL = """
CREATE TABLE IF NOT EXISTS magic_links (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_by TEXT
)
"""


def create_magic_link(
    store: Any,
    *,
    user_id: str,
    ttl_seconds: int = 300,
    created_by: str = "cli",
) -> str:
    """Create a one-time magic link token.

    Args:
        store: AuthStore instance (uses _execute_modify).
        user_id: Target user ID.
        ttl_seconds: Token lifetime in seconds (default: 5 minutes).
        created_by: Who created this token (for audit).

    Returns:
        URL-safe token string (43 chars).
    """
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat()

    store._execute_modify(
        "INSERT INTO magic_links (token, user_id, expires_at, created_by) VALUES (%s, %s, %s, %s)",
        (token, str(user_id), expires_at, created_by),
    )

    return token


def validate_magic_link(store: Any, token: str) -> str | None:
    """Validate and consume a magic link token.

    Returns the user_id if valid, None if expired/used/unknown.
    The token is marked as used on successful validation (single-use).
    """
    rows = store._execute(
        "SELECT user_id, expires_at, used_at FROM magic_links WHERE token = %s",
        (token,),
    )

    if not rows:
        return None

    row = rows[0]

    # Already used
    if row["used_at"] is not None:
        return None

    # Expired
    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.now(UTC) > expires_at:
        return None

    # Mark as used
    store._execute_modify(
        "UPDATE magic_links SET used_at = %s WHERE token = %s",
        (datetime.now(UTC).isoformat(), token),
    )

    return row["user_id"]
```

- [ ] **Step 4: Add magic_links table to AuthStore._init_db**

In `src/dazzle_back/runtime/auth/store.py`, in `_init_db()`, after the `password_reset_tokens` CREATE TABLE block, add:

```python
            # Magic link tokens for one-time authentication (#695)
            from dazzle_back.runtime.auth.magic_link import MAGIC_LINKS_DDL

            cursor.execute(MAGIC_LINKS_DDL)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_magic_link.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_back/runtime/auth/magic_link.py src/dazzle_back/runtime/auth/store.py tests/unit/test_magic_link.py
git commit -m "feat: magic link primitive — one-time login tokens (#695)"
```

---

### Task 4: `impersonate` CLI Command

**Files:**
- Modify: `src/dazzle/cli/auth.py`
- Test: `tests/unit/test_impersonate.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_impersonate.py`:

```python
"""Tests for dazzle auth impersonate command (#695)."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

runner = CliRunner()


class TestImpersonateCommand:
    @patch("dazzle.cli.auth._get_auth_store")
    def test_cookie_mode_prints_session(self, mock_store_fn):
        """Default mode prints the session cookie value."""
        mock_store = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-uuid-1"
        mock_user.email = "teacher@school.uk"
        mock_session = MagicMock()
        mock_session.id = "session-token-abc"
        mock_store.get_user_by_email.return_value = mock_user
        mock_store.create_session.return_value = mock_session
        mock_store_fn.return_value = mock_store

        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["impersonate", "teacher@school.uk"])
        assert result.exit_code == 0
        assert "session-token-abc" in result.output

    @patch("dazzle.cli.auth.create_magic_link")
    @patch("dazzle.cli.auth._get_auth_store")
    def test_url_mode_prints_magic_link(self, mock_store_fn, mock_create):
        """--url mode prints a one-time login URL."""
        mock_store = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-uuid-1"
        mock_user.email = "teacher@school.uk"
        mock_store.get_user_by_email.return_value = mock_user
        mock_store_fn.return_value = mock_store
        mock_create.return_value = "test-token-xyz"

        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["impersonate", "teacher@school.uk", "--url"])
        assert result.exit_code == 0
        assert "/_auth/magic/test-token-xyz" in result.output

    @patch("dazzle.cli.auth._get_auth_store")
    def test_user_not_found(self, mock_store_fn):
        """Prints error and exits 1 when user not found."""
        mock_store = MagicMock()
        mock_store.get_user_by_email.return_value = None
        mock_store_fn.return_value = mock_store

        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["impersonate", "nobody@example.com"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    @patch("dazzle.cli.auth._get_auth_store")
    def test_json_output(self, mock_store_fn):
        """--json produces JSON output."""
        mock_store = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-uuid-1"
        mock_user.email = "teacher@school.uk"
        mock_session = MagicMock()
        mock_session.id = "session-abc"
        mock_store.get_user_by_email.return_value = mock_user
        mock_store.create_session.return_value = mock_session
        mock_store_fn.return_value = mock_store

        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["impersonate", "teacher@school.uk", "--json"])
        assert result.exit_code == 0
        assert '"session_id"' in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_impersonate.py -v`
Expected: FAIL

- [ ] **Step 3: Implement impersonate command**

Add to `src/dazzle/cli/auth.py`. First add the import near the top (after existing imports):

```python
from dazzle_back.runtime.auth.magic_link import create_magic_link
```

Then add the command:

```python
def _parse_ttl(ttl_str: str) -> int:
    """Parse a TTL string like '5m', '1h', '30s' into seconds."""
    units = {"s": 1, "m": 60, "h": 3600}
    if ttl_str[-1] in units:
        return int(ttl_str[:-1]) * units[ttl_str[-1]]
    return int(ttl_str)


@auth_app.command(name="impersonate")
def impersonate(
    identifier: Annotated[str, typer.Argument(help="User email or UUID")],
    url: Annotated[bool, typer.Option("--url", help="Generate a one-time login URL instead of cookie")] = False,
    ttl: Annotated[str, typer.Option("--ttl", help="Session/token TTL (e.g. 5m, 1h, 30s)")] = "30m",
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Generate a session or one-time login URL for any user.

    Default: prints a session cookie value for curl/devtools.
    With --url: prints a magic link URL for browser use.
    """
    import socket
    from datetime import timedelta

    store = _get_auth_store()
    user = _resolve_user(store, identifier)

    if not user:
        console.print(f"[red]User not found: {identifier}[/red]")
        raise typer.Exit(1)

    ttl_seconds = _parse_ttl(ttl)
    created_by = f"cli@{socket.gethostname()}"

    if url:
        token = create_magic_link(store, user_id=str(user.id), ttl_seconds=ttl_seconds, created_by=created_by)
        link = f"http://localhost:8000/_auth/magic/{token}"

        if output_json:
            console.print_json(json.dumps({"email": user.email, "magic_link": link, "ttl_seconds": ttl_seconds}))
        else:
            console.print(f"[green]Magic link for:[/green] {user.email}")
            console.print(f"  [yellow]{link}[/yellow]")
            console.print(f"  Expires in: {ttl}")
            console.print("  [dim]Single use — link is consumed on first visit.[/dim]")
    else:
        session = store.create_session(user, expires_in=timedelta(seconds=ttl_seconds))

        if output_json:
            console.print_json(json.dumps({
                "email": user.email,
                "session_id": session.id,
                "cookie": f"dazzle_session={session.id}; Path=/; HttpOnly",
                "ttl_seconds": ttl_seconds,
            }))
        else:
            console.print(f"[green]Session created for:[/green] {user.email}")
            console.print(f"  [yellow]Cookie: dazzle_session={session.id}[/yellow]")
            console.print(f"  Expires in: {ttl}")
            console.print("  [dim]Paste in browser devtools or use: curl -b 'dazzle_session=...'[/dim]")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_impersonate.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/auth.py tests/unit/test_impersonate.py
git commit -m "feat: dazzle auth impersonate — session cookie + magic link URL (#695)"
```

---

### Task 5: `rotate-passwords` CLI Command

**Files:**
- Modify: `src/dazzle/cli/auth.py`
- Test: `tests/unit/test_rotate_passwords.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_rotate_passwords.py`:

```python
"""Tests for dazzle auth rotate-passwords command (#695)."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

runner = CliRunner()


class TestRotatePasswordsCommand:
    @patch("dazzle.cli.auth._get_auth_store")
    def test_rotate_all_generate(self, mock_store_fn):
        """--all --generate rotates all users with random passwords."""
        mock_store = MagicMock()
        user1 = MagicMock()
        user1.id = "u1"
        user1.email = "a@test.com"
        user2 = MagicMock()
        user2.id = "u2"
        user2.email = "b@test.com"
        mock_store.list_users.return_value = [user1, user2]
        mock_store.update_password.return_value = True
        mock_store.delete_user_sessions.return_value = 1
        mock_store_fn.return_value = mock_store

        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["rotate-passwords", "--all", "--generate", "--yes"])
        assert result.exit_code == 0
        assert mock_store.update_password.call_count == 2
        assert mock_store.delete_user_sessions.call_count == 2
        assert "a@test.com" in result.output
        assert "b@test.com" in result.output

    @patch("dazzle.cli.auth._get_auth_store")
    def test_rotate_by_role(self, mock_store_fn):
        """--role filters users by role."""
        mock_store = MagicMock()
        user1 = MagicMock()
        user1.id = "u1"
        user1.email = "teacher@test.com"
        mock_store.list_users.return_value = [user1]
        mock_store.update_password.return_value = True
        mock_store.delete_user_sessions.return_value = 0
        mock_store_fn.return_value = mock_store

        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["rotate-passwords", "--role", "teacher", "--generate", "--yes"])
        assert result.exit_code == 0
        mock_store.list_users.assert_called_once_with(role="teacher")

    @patch("dazzle.cli.auth._get_auth_store")
    def test_rotate_explicit_password(self, mock_store_fn):
        """--password sets the same password for all matched users."""
        mock_store = MagicMock()
        user1 = MagicMock()
        user1.id = "u1"
        user1.email = "a@test.com"
        mock_store.list_users.return_value = [user1]
        mock_store.update_password.return_value = True
        mock_store.delete_user_sessions.return_value = 0
        mock_store_fn.return_value = mock_store

        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["rotate-passwords", "--all", "--password", "NewSecure123", "--yes"])
        assert result.exit_code == 0
        mock_store.update_password.assert_called_once_with("u1", "NewSecure123")

    @patch("dazzle.cli.auth._get_auth_store")
    def test_requires_yes(self, mock_store_fn):
        """Without --yes, prompts for confirmation."""
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["rotate-passwords", "--all", "--generate"], input="n\n")
        assert result.exit_code != 0

    @patch("dazzle.cli.auth._get_auth_store")
    def test_requires_generate_or_password(self, mock_store_fn):
        """Must specify either --generate or --password."""
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["rotate-passwords", "--all", "--yes"])
        assert result.exit_code == 1

    @patch("dazzle.cli.auth._get_auth_store")
    def test_requires_all_or_role(self, mock_store_fn):
        """Must specify either --all or --role."""
        from dazzle.cli.auth import auth_app

        result = runner.invoke(auth_app, ["rotate-passwords", "--generate", "--yes"])
        assert result.exit_code == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_rotate_passwords.py -v`
Expected: FAIL

- [ ] **Step 3: Implement rotate-passwords command**

Add to `src/dazzle/cli/auth.py`:

```python
@auth_app.command(name="rotate-passwords")
def rotate_passwords(
    all_users: Annotated[bool, typer.Option("--all", help="Rotate for all users")] = False,
    role: Annotated[str | None, typer.Option("--role", "-r", help="Rotate only for users with this role")] = None,
    generate: Annotated[bool, typer.Option("--generate", "-g", help="Generate random passwords")] = False,
    password: Annotated[str | None, typer.Option("--password", "-p", help="Set explicit password for all users")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Rotate passwords for multiple users at once."""
    if not all_users and not role:
        console.print("[red]Specify --all or --role to select users.[/red]")
        raise typer.Exit(1)

    if not generate and not password:
        console.print("[red]Specify --generate or --password.[/red]")
        raise typer.Exit(1)

    if generate and password:
        console.print("[red]Use --generate or --password, not both.[/red]")
        raise typer.Exit(1)

    if password and len(password) < _MIN_PASSWORD_LENGTH:
        console.print(f"[red]Password must be at least {_MIN_PASSWORD_LENGTH} characters.[/red]")
        raise typer.Exit(1)

    store = _get_auth_store()

    if role:
        users = store.list_users(role=role)
    else:
        users = store.list_users()

    if not users:
        console.print("[yellow]No matching users found.[/yellow]")
        raise typer.Exit(0)

    if not yes:
        confirm = typer.confirm(f"Rotate passwords for {len(users)} user(s)?")
        if not confirm:
            raise typer.Abort()

    results: list[dict[str, Any]] = []
    for user in users:
        new_pw = _generate_temp_password() if generate else password
        store.update_password(user.id, new_pw)
        revoked = store.delete_user_sessions(user.id)
        entry: dict[str, Any] = {"email": user.email, "sessions_revoked": revoked}
        if generate:
            entry["password"] = new_pw
        results.append(entry)

    if output_json:
        console.print_json(json.dumps({"rotated": len(results), "users": results}))
    else:
        table = Table(title=f"Rotated {len(results)} password(s)")
        table.add_column("Email")
        if generate:
            table.add_column("New Password")
        table.add_column("Sessions Revoked")
        for r in results:
            row = [r["email"]]
            if generate:
                row.append(r["password"])
            row.append(str(r["sessions_revoked"]))
            table.add_row(*row)
        console.print(table)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rotate_passwords.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/auth.py tests/unit/test_rotate_passwords.py
git commit -m "feat: dazzle auth rotate-passwords — bulk password rotation (#695)"
```

---

### Task 6: `dbshell` Command

**Files:**
- Create: `src/dazzle/cli/dbshell.py`
- Modify: `src/dazzle/cli/__init__.py`
- Test: `tests/unit/test_dbshell.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_dbshell.py`:

```python
"""Tests for dazzle dbshell command (#695)."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

runner = CliRunner()


class TestDbshellCommand:
    @patch("dazzle.cli.dbshell.subprocess")
    @patch("dazzle.cli.dbshell.shutil.which", return_value="/usr/bin/psql")
    @patch("dazzle.cli.dbshell._resolve_db_url", return_value="postgresql://localhost/myapp")
    def test_basic_invocation(self, mock_url, mock_which, mock_subprocess):
        """dbshell calls psql with DATABASE_URL."""
        from dazzle.cli.dbshell import dbshell_command

        from dazzle.cli import app

        result = runner.invoke(app, ["dbshell"])
        mock_subprocess.run.assert_called_once()
        args = mock_subprocess.run.call_args[0][0]
        assert args[0] == "psql"
        assert "postgresql://localhost/myapp" in args

    @patch("dazzle.cli.dbshell.subprocess")
    @patch("dazzle.cli.dbshell.shutil.which", return_value="/usr/bin/psql")
    @patch("dazzle.cli.dbshell._resolve_db_url", return_value="postgresql://localhost/myapp")
    def test_single_query(self, mock_url, mock_which, mock_subprocess):
        """dbshell -c passes query to psql."""
        from dazzle.cli import app

        result = runner.invoke(app, ["dbshell", "-c", "SELECT 1"])
        args = mock_subprocess.run.call_args[0][0]
        assert "-c" in args
        assert "SELECT 1" in args

    @patch("dazzle.cli.dbshell.subprocess")
    @patch("dazzle.cli.dbshell.shutil.which", return_value="/usr/bin/psql")
    @patch("dazzle.cli.dbshell._resolve_db_url", return_value="postgresql://localhost/myapp")
    def test_read_only(self, mock_url, mock_which, mock_subprocess):
        """--read-only passes the read-only flag to psql."""
        from dazzle.cli import app

        result = runner.invoke(app, ["dbshell", "--read-only"])
        args = mock_subprocess.run.call_args[0][0]
        assert "-v" in args
        assert "default_transaction_read_only=on" in args

    @patch("dazzle.cli.dbshell.shutil.which", return_value=None)
    @patch("dazzle.cli.dbshell._resolve_db_url", return_value="postgresql://localhost/myapp")
    def test_psql_not_found(self, mock_url, mock_which):
        """Error when psql is not installed."""
        from dazzle.cli import app

        result = runner.invoke(app, ["dbshell"])
        assert result.exit_code == 1
        assert "psql" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_dbshell.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement dbshell.py**

Create `src/dazzle/cli/dbshell.py`:

```python
"""Database shell command — drop into psql with app's DATABASE_URL."""

import shutil
import subprocess
from typing import Annotated

import typer
from rich.console import Console

console = Console()


def _resolve_db_url(database_url: str | None = None) -> str:
    """Resolve database URL from explicit arg, manifest, or env."""
    from dazzle.core.manifest import load_manifest, resolve_database_url

    from pathlib import Path

    manifest = None
    manifest_path = Path.cwd() / "dazzle.toml"
    if manifest_path.exists():
        manifest = load_manifest(manifest_path)
    return resolve_database_url(manifest, explicit_url=database_url or "")


def dbshell_command(
    command: Annotated[str | None, typer.Option("-c", help="Run a single SQL command")] = None,
    read_only: Annotated[bool, typer.Option("--read-only", help="Connect in read-only mode")] = False,
    database_url: Annotated[
        str | None,
        typer.Option("--database-url", envvar="DATABASE_URL", help="PostgreSQL database URL"),
    ] = None,
) -> None:
    """Open an interactive PostgreSQL shell (psql) with the app's database."""
    psql_path = shutil.which("psql")
    if not psql_path:
        console.print("[red]psql not found.[/red] Install PostgreSQL client tools:")
        console.print("  macOS: brew install libpq && brew link --force libpq")
        console.print("  Ubuntu: sudo apt install postgresql-client")
        raise typer.Exit(1)

    url = _resolve_db_url(database_url)
    if not url:
        console.print("[red]No DATABASE_URL found.[/red] Set it in dazzle.toml, environment, or --database-url.")
        raise typer.Exit(1)

    args = ["psql", url]
    if command:
        args.extend(["-c", command])
    if read_only:
        args.extend(["-v", "default_transaction_read_only=on"])

    subprocess.run(args, check=False)
```

- [ ] **Step 4: Register in `__init__.py`**

Add to `src/dazzle/cli/__init__.py`. Find the block where runtime commands are registered (around line 192) and add:

```python
from dazzle.cli.dbshell import dbshell_command
app.command(name="dbshell")(dbshell_command)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_dbshell.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/cli/dbshell.py src/dazzle/cli/__init__.py tests/unit/test_dbshell.py
git commit -m "feat: dazzle dbshell — zero-config psql access (#695)"
```

---

### Task 7: Lint + Full Test Suite

**Files:** None (validation only)

- [ ] **Step 1: Run ruff**

Run: `ruff check src/dazzle/cli/auth.py src/dazzle/cli/dbshell.py src/dazzle_back/runtime/auth/magic_link.py src/dazzle_back/runtime/auth/store.py --fix && ruff format src/dazzle/cli/auth.py src/dazzle/cli/dbshell.py src/dazzle_back/runtime/auth/magic_link.py src/dazzle_back/runtime/auth/store.py`
Expected: Clean

- [ ] **Step 2: Run mypy**

Run: `mypy src/dazzle/cli/auth.py src/dazzle/cli/dbshell.py src/dazzle_back/runtime/auth/magic_link.py --ignore-missing-imports`
Expected: No errors

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -m "not e2e" --timeout=120 -q`
Expected: All pass

- [ ] **Step 4: Commit any fixes**

```bash
git add -u
git commit -m "chore: lint + type fixes for admin CLI commands (#695)"
```
