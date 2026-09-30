"""A failed DB statement must be recovered before the connection is reused.

Why this exists
---------------
``repository._resolve_latest_one_fields`` probed a temporal end column by
guessing: execute, catch, re-execute with the alternate name. Nothing in
``pg_backend.py`` passes ``autocommit=``, so psycopg3 leaves the transaction
open and **PostgreSQL marks it ABORTED** the instant the first statement
errors. Every subsequent statement on that connection then fails with
``InFailedSqlTransaction`` until a rollback. The retry therefore could never
succeed: the documented ``effective_to`` fallback was unreachable, and a soft
column-name mismatch surfaced as a hard 500 on any ``as_of`` time-travel read.

The existing exception gates all key on the *body* of the handler — silent,
trivial, single-statement (``test_swallow_ratchet``,
``test_no_bare_except_pass``). A 20-statement handler that re-executes is
counted by none of them, and none of them models resource state across the
``except`` boundary. This gate keys on that boundary instead.

What this catches
-----------------
An ``except`` handler that re-runs a statement on a cursor/connection whose
previous statement failed, without first rolling back, opening a savepoint, or
re-acquiring the connection.

How to satisfy it
-----------------
``conn.rollback()`` before the retry, or wrap the pair in
``conn.transaction()`` (psycopg3 savepoint), or re-acquire via
``with db.connection()``. If a failure really is terminal, add a
``# DZ-DB-NO-RETRY <reason>`` marker on the handler line.

What this does NOT catch
------------------------
It cannot prove a rollback is *sufficient* — only that one is present. It also
does not model a rollback that would discard work the outer transaction needs;
``test_repository_temporal_retry.py`` exercises the real branch with a fake that
models the psycopg3 abort rule.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

_ROOTS = [Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http"]

# Names that are almost certainly a DB handle. Deliberately narrow: a bare
# `x.execute(...)` on an arbitrary object is not enough to assert a transaction.
_HANDLE_NAMES = {"cursor", "cur", "conn", "connection", "self._cursor", "self._conn"}
_RECOVERY_ATTRS = {"rollback", "commit", "transaction", "savepoint", "cursor"}
_MARKER = "DZ-DB-NO-RETRY"
_SQL_MARKERS = ("ROLLBACK", "SAVEPOINT", "BEGIN")


def _receiver_name(call: ast.Call) -> str | None:
    """`cursor.execute` -> "cursor"; anything else -> None."""
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != "execute":
        return None
    recv = func.value
    if isinstance(recv, ast.Name):
        return recv.id
    if isinstance(recv, ast.Attribute):
        return recv.attr
    return None


def _is_recovery(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr in _RECOVERY_ATTRS:
            return True
        if isinstance(node.func, ast.Name) and node.func.id in {"connection", "connect"}:
            return True
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return any(marker in node.value.upper() for marker in _SQL_MARKERS)
    return False


def _unrecovered_retries(handler: ast.ExceptHandler) -> list[int]:
    """Line numbers of retried `execute` calls with no *prior* recovery.

    Order matters: a recovery call that appears AFTER the retry does not help,
    and neither does one inside a sibling `except` block. A rollback elsewhere in
    the handler body is not recovery for a statement that already failed.
    """
    retries: list[tuple[int, int]] = []  # (lineno, recovery_lineno_or_-1)
    recoveries: list[int] = []
    for node in ast.walk(handler):
        if _is_recovery(node):
            line = getattr(node, "lineno", -1)
            if line != -1:
                recoveries.append(line)
        if isinstance(node, ast.Call):
            if _receiver_name(node) is not None:
                retries.append((getattr(node, "lineno", -1), -1))
    if not retries:
        return []
    unrecovered: list[int] = []
    for retry_line, _ in retries:
        prior = [r for r in recoveries if r != -1 and r < retry_line]
        if not prior:
            unrecovered.append(retry_line)
    return unrecovered


def _handlers_retrying_without_recovery(path: Path) -> list[int]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    lines = text.splitlines()
    hits: list[int] = []
    for handler in ast.walk(tree):
        if not isinstance(handler, ast.ExceptHandler):
            continue
        unrecovered = _unrecovered_retries(handler)
        if not unrecovered:
            continue
        # Honour the escape hatch: a marker on the handler line or nearby.
        window = lines[max(0, handler.lineno - 3) : handler.lineno]
        if any(_MARKER in line for line in window):
            continue
        hits.append(handler.lineno)
    return hits


def test_no_db_retry_without_recovery() -> None:
    """Retrying a statement on an aborted connection always raises.

    `db.connection()` does not enable autocommit, so after a failed statement
    PostgreSQL aborts the transaction and every later statement fails with
    InFailedSqlTransaction until a rollback. Roll back / savepoint / re-acquire
    before retrying, or mark the handler `# DZ-DB-NO-RETRY <reason>`.
    """
    hits: list[str] = []
    for root in _ROOTS:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            for lineno in _handlers_retrying_without_recovery(path):
                hits.append(f"{path.relative_to(Path.cwd())}:{lineno}")
    assert not hits, (
        "A handler retries a cursor statement after a failure with no recovery. "
        "On a non-autocommit psycopg3 connection the transaction is already "
        "aborted, so the retry raises InFailedSqlTransaction and the fallback is "
        "unreachable. Add conn.rollback() (or conn.transaction() / re-acquire) "
        f"before the retry, or mark the handler `# {_MARKER} <reason>`:\n  " + "\n  ".join(hits)
    )


# --- Detector self-tests -----------------------------------------------------
#
# A gate that passes for the wrong reason looks identical to one that passes for
# the right reason. The first draft of this gate did exactly that: it walked the
# whole handler for a recovery call and found one in a *sibling* `except`, so it
# passed the un-fixed code. The gate below was only correct once it was made to
# assert that its own detector fires.
#
# These tests run the detector over synthetic source, so the check is about the
# check — independent of whether the current tree happens to be clean.


def _detect(tmp_path, body: str) -> list[int]:
    path = tmp_path / "sample_runtime.py"
    path.write_text(body, encoding="utf-8")
    return _handlers_retrying_without_recovery(path)


def test_detector_flags_retry_without_recovery(tmp_path) -> None:
    """The bug shape: execute, catch, re-execute on the same cursor."""
    hits = _detect(
        tmp_path,
        "def f(db):\n"
        "    conn = db.connection()\n"
        "    cursor = conn.cursor()\n"
        "    try:\n"
        "        cursor.execute(sql, params)\n"
        "    except Exception:\n"
        "        cursor.execute(other_sql, params)\n",
    )
    assert hits == [6], f"expected the handler at line 6 flagged, got {hits}"


def test_detector_accepts_rollback_before_the_retry(tmp_path) -> None:
    """Recovery *before* the retry is the fix; the detector must accept it."""
    assert (
        _detect(
            tmp_path,
            "def f(db):\n"
            "    conn = db.connection()\n"
            "    cursor = conn.cursor()\n"
            "    try:\n"
            "        cursor.execute(sql, params)\n"
            "    except Exception:\n"
            "        conn.rollback()\n"
            "        cursor.execute(other_sql, params)\n",
        )
        == []
    )


def test_detector_rejects_recovery_after_the_retry(tmp_path) -> None:
    """A rollback that comes *after* the retry does not help the retry.

    This is the exact hole in the first draft: the walk found the rollback in the
    handler without regard to order, so the un-fixed code passed.
    """
    hits = _detect(
        tmp_path,
        "def f(db):\n"
        "    conn = db.connection()\n"
        "    cursor = conn.cursor()\n"
        "    try:\n"
        "        cursor.execute(sql, params)\n"
        "    except Exception:\n"
        "        try:\n"
        "            cursor.execute(other_sql, params)\n"
        "        finally:\n"
        "            conn.rollback()\n",
    )
    assert hits == [6], f"recovery after the retry must not count, got {hits}"


def test_detector_ignores_handlers_that_do_not_retry(tmp_path) -> None:
    """A plain catch that re-raises is not in scope for this gate."""
    assert (
        _detect(
            tmp_path,
            "def f(db):\n"
            "    try:\n"
            "        risky()\n"
            "    except Exception:\n"
            "        logger.warning('nope')\n"
            "        raise\n",
        )
        == []
    )


def test_detector_honours_the_escape_hatch(tmp_path) -> None:
    """`# DZ-DB-NO-RETRY <reason>` suppresses the finding, as documented."""
    assert (
        _detect(
            tmp_path,
            "def f(db):\n"
            "    try:\n"
            "        cursor.execute(sql)\n"
            "    except Exception:  # DZ-DB-NO-RETRY terminal, must propagate\n"
            "        cursor.execute(other)\n",
        )
        == []
    )
