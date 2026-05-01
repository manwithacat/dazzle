"""Tests for #975 — Alpine error handler converts plain-object throws to real Errors.

Background: Alpine 3's default error handler does
  setTimeout(() => { throw {message, el, expression} }, 0)

The thrown value is a plain object. Playwright's `page.on('pageerror')`
sees String(obj), which strips to `[object Object]` — opaque, no
message, no stack. AegisMark's site-fuzz captured these as "Object
thrown as page-error" with no diagnostic content (#975).

Fix: install a custom Alpine error handler in `dz-alpine.js` that
wraps the raw error in a `new Error(...)` with a descriptive message
and the original error attached as `cause`. Site-fuzz harnesses now
see `Alpine expression error: <message> (expression: <expr>)` — the
failing expression text itself becomes diagnostic.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DZ_ALPINE = REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "js" / "dz-alpine.js"


def test_custom_alpine_error_handler_installed() -> None:
    """`Alpine.setErrorHandler` must be invoked at alpine:init."""
    js = DZ_ALPINE.read_text()
    assert "Alpine.setErrorHandler" in js, (
        "Missing custom Alpine error handler — site-fuzz harnesses "
        "see Alpine errors as opaque '[object Object]' without it (#975)."
    )


def test_handler_wraps_in_real_error() -> None:
    """The handler must construct a `new Error(...)` so stack + message survive."""
    js = DZ_ALPINE.read_text()
    # Locate the setErrorHandler block.
    idx = js.find("Alpine.setErrorHandler")
    assert idx >= 0
    # Read enough following bytes to capture the full callback.
    block = js[idx : idx + 1000]
    assert "new Error(" in block, (
        "Custom Alpine error handler must wrap the raw error in `new Error(...)` "
        "so Playwright's pageerror handler gets a real Error with stack (#975)."
    )


def test_handler_includes_expression_in_message() -> None:
    """The wrapped error message must surface the failing expression text."""
    js = DZ_ALPINE.read_text()
    idx = js.find("Alpine.setErrorHandler")
    block = js[idx : idx + 1000]
    assert "expression" in block and "Alpine expression error" in block, (
        "The wrapped Error message must include the failing expression text — "
        "without it the diagnostic improvement vs the default handler is "
        "negligible (#975)."
    )


def test_handler_attaches_cause() -> None:
    """The wrapped error must preserve the original via `.cause`."""
    js = DZ_ALPINE.read_text()
    idx = js.find("Alpine.setErrorHandler")
    block = js[idx : idx + 1000]
    assert "err.cause" in block or ".cause =" in block, (
        "Custom Alpine error handler should preserve the original error "
        "via err.cause for downstream debugging (#975)."
    )


def test_handler_throws_via_setTimeout() -> None:
    """The handler must preserve Alpine's async-throw shape (setTimeout 0)."""
    js = DZ_ALPINE.read_text()
    idx = js.find("Alpine.setErrorHandler")
    block = js[idx : idx + 1000]
    assert "setTimeout" in block, (
        "Custom handler must throw via setTimeout(..., 0) to preserve "
        "Alpine's async-throw shape — synchronous throws would break "
        "in-flight evaluation (#975)."
    )
