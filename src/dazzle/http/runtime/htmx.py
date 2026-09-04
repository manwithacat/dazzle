"""
HTMX-aware response utilities.

Provides helpers for building HTMLResponse objects with HX-* headers
for server-client event coordination (triggers, retarget, reswap, redirect).

This is the canonical location for HTMX presentation logic.  The
``dazzle.http.runtime.htmx_response`` module re-exports from here for
backward compatibility.
"""

from __future__ import annotations  # required: forward reference

import json
from dataclasses import dataclass
from typing import Any

from fastapi.responses import HTMLResponse, JSONResponse

from dazzle.render.breadcrumbs import clerk_entity_noun, clerk_mutation_toast_title
from dazzle.render.filters import clerk_form_error_field_label

_ERROR_LOC_ENVELOPES = frozenset({"body", "query", "path", "header", "cookie"})


@dataclass(frozen=True, slots=True)
class HtmxDetails:
    """Parsed HTMX request headers -- single source of truth.

    Parses all 8 HX-* request headers sent by htmx:
    https://htmx.org/reference/#request_headers
    """

    is_htmx: bool = False
    is_boosted: bool = False
    current_url: str = ""
    is_history_restore: bool = False
    prompt: str = ""
    target: str = ""
    trigger_id: str = ""
    trigger_name: str = ""

    @classmethod
    def from_request(cls, request: Any) -> HtmxDetails:
        """Construct from a Starlette/FastAPI request."""
        if not hasattr(request, "headers"):
            return cls()
        h = request.headers
        return cls(
            is_htmx=h.get("HX-Request") == "true",
            is_boosted=h.get("HX-Boosted") == "true",
            current_url=h.get("HX-Current-URL", ""),
            is_history_restore=h.get("HX-History-Restore-Request") == "true",
            prompt=h.get("HX-Prompt", ""),
            target=h.get("HX-Target", ""),
            trigger_id=h.get("HX-Trigger", ""),
            trigger_name=h.get("HX-Trigger-Name", ""),
        )

    @property
    def wants_partial(self) -> bool:
        """Boosted navigation that is NOT a history restore -> body-only."""
        return self.is_boosted and not self.is_history_restore

    @property
    def wants_fragment(self) -> bool:
        """Navigation targeting #main-content -> content-only response."""
        return self.is_htmx and self.target == "main-content" and not self.is_history_restore

    @property
    def wants_drawer(self) -> bool:
        """Navigation targeting detail drawer -> content-only response."""
        return self.is_htmx and self.target == "dz-detail-drawer-content"


def htmx_response(
    content: str,
    *,
    status_code: int = 200,
    triggers: dict[str, Any] | list[str] | None = None,
    trigger_after_swap: dict[str, Any] | list[str] | None = None,
    retarget: str | None = None,
    reswap: str | None = None,
    redirect: str | None = None,
) -> HTMLResponse:
    """Create an HTMLResponse with HTMX headers.

    Args:
        content: HTML body content.
        status_code: HTTP status code (default 200).
        triggers: Events to fire on the client via HX-Trigger.
            - list[str]: simple event names (no payload)
            - dict[str, Any]: event names with JSON payloads
        trigger_after_swap: Events fired after the swap completes.
        retarget: CSS selector to override the triggering element's hx-target.
        reswap: Override the triggering element's hx-swap strategy.
        redirect: URL to redirect the client to via HX-Redirect.

    Returns:
        HTMLResponse with appropriate HX-* headers set.
    """
    headers: dict[str, str] = {}

    if triggers:
        headers["HX-Trigger"] = _encode_trigger(triggers)
    if trigger_after_swap:
        headers["HX-Trigger-After-Swap"] = _encode_trigger(trigger_after_swap)
    if retarget:
        headers["HX-Retarget"] = retarget
    if reswap:
        headers["HX-Reswap"] = reswap
    if redirect:
        headers["HX-Redirect"] = redirect

    return HTMLResponse(content=content, status_code=status_code, headers=headers)


# Mutation toast default body copy (showToast detail → dz-toast host).
# Titles use clerk_mutation_toast_title (oral #239).
_MUTATION_TOAST_MESSAGE: dict[str, str] = {
    "created": "{entity} was created",
    "updated": "{entity} was updated",
    "deleted": "{entity} was deleted",
}


def htmx_trigger_headers(
    entity_name: str,
    action: str,
    message: str | None = None,
    *,
    title: str | None = None,
    view_url: str | None = None,
    entity_labels: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build HX-Trigger header dict for entity mutation responses.

    Fires ``entity{Action}`` plus ``showToast`` with structured slots the
    ``dz-toast`` host understands (title, message, optional actions).

    Args:
        entity_name: Name of the entity (e.g. "Task").
        action: Mutation action ("created", "updated", "deleted").
        message: Optional toast body. If None, auto-generated.
        title: Optional toast title. If None, action-derived default.
        view_url: When set (and no full-page redirect is taking the user
            there already), emit a "View" action link on the toast.
        entity_labels: Optional ``entity_slug`` / name → clerk title catalog
            (oral #192). PascalCase names still split without a catalog.

    Returns:
        Dictionary with "HX-Trigger" key ready to pass to Response headers.
    """
    event_name = f"entity{action.capitalize()}"
    noun = clerk_entity_noun(entity_name, entity_labels)
    toast_title = clerk_mutation_toast_title(
        entity_name, entity_labels, action=action, authored=title or ""
    )
    toast_message = message or _MUTATION_TOAST_MESSAGE.get(
        action, f"{noun} {action} successfully"
    ).format(entity=noun)
    toast: dict[str, Any] = {
        "message": toast_message,
        "type": "success",
        "title": toast_title,
    }
    if view_url:
        toast["actions"] = [{"label": "View", "href": view_url}]
    trigger = {
        event_name: {"entity": entity_name},
        "showToast": toast,
    }
    return {"HX-Trigger": json.dumps(trigger)}


def is_htmx_request(request: Any) -> bool:
    """Check if the incoming request is from HTMX."""
    return HtmxDetails.from_request(request).is_htmx


def is_peek_request(request: Any) -> bool:
    """Whether this is a #1494 row-peek fetch (`peek: expand`).

    The list-row chevron loads an entity's detail *body* into an inline panel
    via ``hx-get="<detail-url>?peek=1"``. Such a request must return the
    content-only body (no app chrome, and crucially no ``dz:titleUpdate``
    trigger — expanding a row must not retitle the page). A direct browser GET
    of the same URL (no ``HX-Request``) is an ordinary full-page detail view.
    """
    if not is_htmx_request(request):
        return False
    params = getattr(request, "query_params", None)
    if params is None:
        return False
    return bool(params.get("peek") == "1")


def htmx_error_response(
    errors: list[str],
    *,
    status_code: int = 422,
) -> HTMLResponse:
    """Create an HTMX-aware validation error response.

    Phase 4 (v0.67.61): inline-rendered with the same CSS classes the
    legacy `fragments/form_errors.html` template emitted, so existing
    styles continue to apply unchanged. Returns the rendered HTML with
    HX-Retarget/#form-errors so HTMX swaps the error into the correct
    container instead of replacing the entire page body.

    Args:
        errors: List of human-readable error messages.
        status_code: HTTP status code (default 422).

    Returns:
        HTMLResponse targeting #form-errors with reswap.
    """
    if errors:
        items_html = "".join(f"<li>{_escape(str(e))}</li>" for e in errors)
        html = (
            '<div class="dz-form-errors" role="alert" aria-live="assertive" data-dazzle-error>'
            '<svg xmlns="http://www.w3.org/2000/svg" class="dz-form-errors-icon" '
            'fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" '
            'aria-hidden="true">'
            '<path stroke-linecap="round" stroke-linejoin="round" '
            'd="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 '
            "2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 "
            '0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />'
            "</svg>"
            '<div class="dz-form-errors-body">'
            '<h3 class="dz-form-errors-title">Validation Error</h3>'
            f'<ul class="dz-form-errors-list" role="list">{items_html}</ul>'
            "</div>"
            "</div>"
        )
    else:
        html = ""

    return htmx_response(
        html,
        status_code=status_code,
        retarget="#form-errors",
        reswap="innerHTML",
        triggers={
            "showToast": {
                "title": "Validation error",
                "message": "Please fix the errors below",
                "type": "error",
            }
        },
    )


def _encode_trigger(value: dict[str, Any] | list[str]) -> str:
    """Encode trigger value to HX-Trigger header format."""
    if isinstance(value, list):
        # Simple event names -- join with commas
        if all(isinstance(v, str) for v in value):
            return ", ".join(value)
        return json.dumps(value)
    return json.dumps(value)


def _escape(s: str) -> str:
    """Minimal HTML escape for error messages."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def json_or_htmx_error(
    request: Any,
    errors: list[dict[str, Any]],
    error_type: str = "validation_error",
) -> HTMLResponse | JSONResponse:
    """Return HTMX error response for HTMX requests, JSON for API clients.

    For form-submission contexts (POST/PUT/PATCH), retargets to
    `#form-errors` so the form's error region renders the messages
    in place — the create/edit form pattern.

    For read contexts (GET — sort, filter, list paging), there's
    no form on the page so the form-errors retarget would trigger
    htmx:targetError. Returns a toast-only response (200 with an
    HX-Trigger showToast) so the user sees the error without the
    htmx machinery breaking. Closes #994.

    Args:
        request: The incoming request.
        errors: Pydantic-style error dicts.
        error_type: Error type string for JSON response.

    Returns:
        HTMLResponse with HX-Retarget for form contexts, toast-only
        HTMLResponse for read contexts, JSONResponse for API clients.
    """
    if is_htmx_request(request):
        messages = _errors_to_messages(errors)
        method = (getattr(request, "method", "") or "").upper()
        # Form-context detection: only retarget #form-errors when the
        # request originated from a form input. Pre-fix, any non-GET
        # request 422'd with HX-Retarget #form-errors regardless of
        # whether the page actually had that element. Chaos-monkey
        # clicks on non-form hx-post buttons (bulk actions, toggles,
        # nav buttons) flooded the console with htmx:targetError on
        # pages without forms.
        #
        # `HX-Trigger-Name` is the `name` attribute of the triggering
        # element. Form inputs always have a `name` (it's how form
        # data is keyed); non-form buttons / hx-* triggers usually
        # don't. Fall back to the toast path when the signal is missing.
        headers = getattr(request, "headers", None)
        trigger_name = ""
        if headers is not None:
            trigger_name = headers.get("HX-Trigger-Name") or headers.get("hx-trigger-name") or ""
        is_form_context = bool(trigger_name) and method != "GET"
        if not is_form_context:
            return htmx_toast_error_response(messages)
        return htmx_error_response(messages)
    return JSONResponse(
        status_code=422,
        content={"detail": errors, "type": error_type},
    )


def htmx_toast_error_response(errors: list[str]) -> HTMLResponse:
    """Surface validation errors via toast, no retarget (#994).

    Used when an HTMX request hits a validation snag in a context
    that has no form-errors target on the page (sort, filter, list
    paging). Returning a 422 with an `HX-Retarget: #form-errors`
    triggers ``htmx:targetError`` because the selector doesn't exist
    — the browser console fills with errors and the user sees
    nothing change.

    Returns 200 with an empty body, no retarget, and an HX-Trigger
    that fires the standard ``showToast`` event. The toast component
    is in the global app shell, so it always exists regardless of
    where the request came from.
    """
    message = "; ".join(errors) if errors else "Request was not accepted"
    return htmx_response(
        "",
        status_code=200,
        triggers={
            "showToast": {
                "title": "Couldn't complete",
                "message": message,
                "type": "error",
            }
        },
    )


def _clerk_error_loc_label(loc: Any) -> str:
    """Last schema loc → clerk form-error field (oral #198).

    Skip HTTP envelopes and list indices. Leftover junk stays put.
    JSON API ``loc`` is unchanged — this labels HTMX speech only.
    """
    names: list[str] = []
    for part in loc or ():
        if isinstance(part, bool) or isinstance(part, int):
            continue
        text = str(part).strip()
        if not text or text.lower() in _ERROR_LOC_ENVELOPES:
            continue
        names.append(text)
    if not names:
        return ""
    return clerk_form_error_field_label(names[-1])


# Pydantic type codes whose default ``Input should be a valid integer/UUID``
# speech dumps Python types (oral #204). value_error / missing stay put —
# enum AfterValidator and "Field required" are already clerk.
_CLERK_TYPE_SPEECH: dict[str, str] = {
    "int_parsing": "number",
    "int_from_float": "number",
    "int_type": "number",
    "float_parsing": "number",
    "float_type": "number",
    "decimal_parsing": "number",
    "decimal_type": "number",
    "bool_parsing": "yes or no",
    "bool_type": "yes or no",
    "uuid_parsing": "id",
    "uuid_type": "id",
    "uuid_version": "id",
    "date_parsing": "date",
    "date_from_datetime_parsing": "date",
    "date_from_datetime": "date",
    "date_type": "date",
    "datetime_parsing": "date and time",
    "datetime_from_date_parsing": "date and time",
    "datetime_from_date": "date and time",
    "datetime_type": "date and time",
    "time_parsing": "time",
    "url_parsing": "web address",
    "url_scheme": "web address",
    "url_type": "web address",
}


def clerk_pydantic_type_speech(err: dict[str, Any] | None) -> str:
    """Pydantic type 422 → clerk speech (oral #204).

    ``Due Date: Input should be a valid date or datetime`` dumped Python
    types while the edit form already says ``Due Date``. Submitted leftover
    junk stays put. JSON ``type`` / ``loc`` / ``msg`` stay the identifiers.
    Unknown codes (``value_error``, ``missing``) keep the original ``msg``.
    """
    payload = err or {}
    raw = str(payload.get("msg") or "").strip()
    kind = str(payload.get("type") or "")
    noun = _CLERK_TYPE_SPEECH.get(kind)
    if not noun:
        return raw or str(payload)
    submitted = payload.get("input")
    leftover = "" if submitted is None else str(submitted)
    if leftover:
        if noun == "number":
            return f"'{leftover}' is not a number"
        if noun == "yes or no":
            return f"'{leftover}' is not yes or no"
        return f"'{leftover}' is not a valid {noun}"
    if noun == "number":
        return "is not a number"
    if noun == "yes or no":
        return "is not yes or no"
    return f"is not a valid {noun}"


_CLERK_LEFTOVER_QUOTE_MAX = 48


def _clerk_leftover_quote(submitted: Any) -> str:
    """Short leftover stays put in speech; long dumps are omitted (form keeps them)."""
    if submitted is None:
        return ""
    leftover = str(submitted)
    if not leftover or len(leftover) > _CLERK_LEFTOVER_QUOTE_MAX:
        return ""
    return leftover


def _clerk_ctx_int(ctx: Any, key: str) -> int | None:
    if not isinstance(ctx, dict) or key not in ctx:
        return None
    try:
        return int(ctx[key])
    except (TypeError, ValueError):
        return None


def _clerk_bound_from_msg(raw: str, token: str) -> int | None:
    lower = raw.lower()
    i = lower.find(token)
    if i < 0:
        return None
    rest = raw[i + len(token) :].strip().split(None, 1)
    if not rest:
        return None
    try:
        return int(rest[0])
    except ValueError:
        return None


def _clerk_with_leftover(leftover: str, rest: str) -> str:
    """``rest`` is a predicate (``is too long (…)`` / ``must be …``)."""
    if leftover:
        return f"'{leftover}' {rest}"
    if rest.startswith("is "):
        return rest[3:]
    return rest


def _clerk_length_speech(leftover: str, *, short: bool, n: int | None) -> str:
    adj = "short" if short else "long"
    if n is None:
        return _clerk_with_leftover(leftover, f"is too {adj}")
    prep = "at least" if short else "at most"
    return _clerk_with_leftover(leftover, f"is too {adj} ({prep} {n} characters)")


def _clerk_slug_constraint_speech(raw: str, leftover: str) -> str | None:
    """Slug AfterValidator 422 → clerk (oral #205). JSON ``msg`` stays the identifier."""
    lower = raw.lower()
    if "slug must" not in lower:
        return None
    if "at least" in lower:
        return _clerk_length_speech(leftover, short=True, n=_clerk_bound_from_msg(raw, "at least"))
    if "at most" in lower:
        return _clerk_length_speech(leftover, short=False, n=_clerk_bound_from_msg(raw, "at most"))
    if "double hyphen" in lower:
        return _clerk_with_leftover(leftover, "must not contain double hyphens")
    if "lowercase" in lower:
        return _clerk_with_leftover(leftover, "must be lowercase letters, digits, and hyphens")
    return _clerk_with_leftover(leftover, "is not a valid slug")


def _clerk_decimal_bound_speech(leftover: str, *, places: bool, n: int | None) -> str:
    """``Decimal input should have no more than N decimal places/digits`` → clerk."""
    noun = "decimal places" if places else "digits"
    if n is None:
        return _clerk_with_leftover(leftover, f"has too many {noun}")
    return _clerk_with_leftover(leftover, f"has too many {noun} (at most {n})")


def clerk_pydantic_constraint_speech(err: dict[str, Any] | None) -> str | None:
    """Length/pattern/decimal-scale 422 → clerk speech (oral #205 / #206).

    ``Title: String should have at most 200 characters`` dumped the Python
    type. ``Slug: Value error, slug must be lowercase…`` dumped the schema
    type (and regex-adjacent rules) while the form already says ``Title`` /
    ``Slug``. ``Amount: Decimal input should have no more than 2 decimal
    places`` dumped the Python type while the create form already says
    ``Amount``. Submitted leftover junk stays put. JSON ``type`` / ``loc`` /
    ``msg`` stay the identifiers. Type-parse / enum / missing stay on their
    helpers. Returns ``None`` when this is not a length/pattern/decimal-scale
    422.
    """
    payload = err or {}
    kind = str(payload.get("type") or "")
    leftover = _clerk_leftover_quote(payload.get("input"))
    ctx = payload.get("ctx")
    if kind == "string_too_long":
        return _clerk_length_speech(leftover, short=False, n=_clerk_ctx_int(ctx, "max_length"))
    if kind == "string_too_short":
        return _clerk_length_speech(leftover, short=True, n=_clerk_ctx_int(ctx, "min_length"))
    if kind == "string_pattern_mismatch":
        return _clerk_with_leftover(leftover, "is not the expected format")
    if kind == "decimal_max_places":
        return _clerk_decimal_bound_speech(
            leftover, places=True, n=_clerk_ctx_int(ctx, "decimal_places")
        )
    if kind == "decimal_max_digits":
        return _clerk_decimal_bound_speech(
            leftover, places=False, n=_clerk_ctx_int(ctx, "max_digits")
        )
    if kind == "decimal_whole_digits":
        return _clerk_decimal_bound_speech(
            leftover, places=False, n=_clerk_ctx_int(ctx, "whole_digits")
        )
    if kind == "value_error":
        return _clerk_slug_constraint_speech(str(payload.get("msg") or ""), leftover)
    return None


def _errors_to_messages(errors: list[dict[str, Any]]) -> list[str]:
    """Convert Pydantic error dicts to clerk-readable HTMX messages."""
    messages = []
    for err in errors:
        loc = err.get("loc", [])
        msg = clerk_pydantic_constraint_speech(err)
        if msg is None:
            msg = clerk_pydantic_type_speech(err)
        field = _clerk_error_loc_label(loc)
        if field:
            messages.append(f"{field}: {msg}")
        else:
            messages.append(msg)
    return messages
