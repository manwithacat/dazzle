"""Event vocabulary v1 — public analytics-event contract (v0.61.0 Phase 4).

Every event Dazzle auto-emits to the analytics dataLayer conforms to the
schema declared here. This is a **public versioned contract**: once users
build GTM triggers or GA4 dashboards against these names, we can't rename
silently. The drift test at ``tests/unit/test_event_vocabulary_v1.py``
pins the exact schema so changes are explicit.

## Versioning rules

- **Additive changes** (new event type, new optional parameter) stay in
  `dz/v1`.
- **Breaking changes** (rename event, remove parameter, change parameter
  type, tighten semantics) cut a new version. Both versions emit in
  parallel for one release cycle, then the old version is removed.
- **CHANGELOG entry** required for any change.

## Event shape (every event)

All events are pushed onto ``window.dataLayer`` with this common structure:

```js
{
    event: "<event_name>",
    dz_schema_version: "1",
    dz_tenant: "<tenant_slug>",       // optional, present in multi-tenant
    ...event-specific parameters
}
```

Parameter values are primitives (string, number, boolean) — no nested
objects. String values are clamped to 100 characters. Parameter names are
snake_case. Event names are prefixed with ``dz_``.

## PII safety

Parameters never include values from `pii()` fields unless the surface
explicitly opts-in via ``analytics: include_pii: [field_name]`` AND the
event schema here declares the parameter as `allow_pii=True`. Phase 4
ships zero PII-allowing parameters by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VOCABULARY_VERSION = "1"
VOCABULARY_ID = "dz/v1"


@dataclass(frozen=True)
class EventParam:
    """One parameter declaration inside an event schema.

    Attributes:
        name: Parameter key in the dataLayer push.
        value_type: Python-ish type name ("str", "int", "float", "bool").
            Clamping / coercion rules live in the JS bus.
        required: Whether every push of this event must include the param.
        description: Human-readable purpose — shown in docs + drift test.
        max_length: For string params, the hard clamp (default 100).
        allow_pii: False by default. If True, callers may opt in to pass
            PII-tagged field values. Phase 4 ships zero of these.
    """

    name: str
    value_type: str
    required: bool = False
    description: str = ""
    max_length: int = 100
    allow_pii: bool = False


@dataclass(frozen=True)
class EventSchema:
    """Declaration of one auto-emitted event in the vocabulary."""

    name: str
    description: str
    fires_on: str
    core_params: tuple[EventParam, ...] = field(default_factory=tuple)
    optional_params: tuple[EventParam, ...] = field(default_factory=tuple)


# Common parameters injected on every event by the JS bus — listed here so
# the drift test can assert their presence.
COMMON_PARAMS: tuple[EventParam, ...] = (
    EventParam(
        name="dz_schema_version",
        value_type="str",
        required=True,
        description=(
            "Schema version of the vocabulary — always equal to "
            "VOCABULARY_VERSION at emission time."
        ),
    ),
    EventParam(
        name="dz_tenant",
        value_type="str",
        required=False,
        description=(
            "Tenant slug for multi-tenant apps. Omitted on single-tenant "
            "deployments. Let GA4 segment by tenant without leaking PII."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Event schemas (dz/v1)
# ---------------------------------------------------------------------------


EVENT_SCHEMAS: tuple[EventSchema, ...] = (
    EventSchema(
        name="dz_page_view",
        description="A workspace surface was viewed — full load or htmx swap.",
        fires_on="htmx:afterSwap into [data-dz-surface] OR initial window.load.",
        core_params=(
            EventParam(
                name="workspace",
                value_type="str",
                required=True,
                description="Workspace identifier (DSL workspace name).",
            ),
            EventParam(
                name="surface",
                value_type="str",
                required=True,
                description="Surface identifier (DSL surface name).",
            ),
        ),
        optional_params=(
            EventParam(
                name="persona_class",
                value_type="str",
                description="Current user's persona role(s), comma-separated.",
            ),
            EventParam(
                name="url",
                value_type="str",
                description="Page URL (without query string).",
                max_length=255,
            ),
            EventParam(
                name="referrer",
                value_type="str",
                description="document.referrer at emission time.",
                max_length=255,
            ),
        ),
    ),
    EventSchema(
        name="dz_action",
        description="A DSL-declared action was invoked (button click, menu item).",
        fires_on=(
            "click on [data-dz-action] elements anywhere in the document (event delegation)."
        ),
        core_params=(
            EventParam(
                name="action_name",
                value_type="str",
                required=True,
                description="DSL action identifier.",
            ),
            EventParam(
                name="entity",
                value_type="str",
                required=True,
                description="Entity the action targets.",
            ),
            EventParam(
                name="surface",
                value_type="str",
                required=True,
                description="Surface containing the action.",
            ),
        ),
        optional_params=(
            EventParam(
                name="entity_id",
                value_type="str",
                description=(
                    "Concrete entity identifier. ONLY included when the "
                    "surface declares `analytics: include_entity_id=true`."
                ),
                allow_pii=False,
            ),
        ),
    ),
    EventSchema(
        name="dz_transition",
        description="A state-machine transition was triggered on an entity.",
        fires_on="State-machine event emitted by the runtime.",
        core_params=(
            EventParam(
                name="entity",
                value_type="str",
                required=True,
                description="Entity whose state changed.",
            ),
            EventParam(
                name="from_state",
                value_type="str",
                required=True,
                description="State name before the transition.",
            ),
            EventParam(
                name="to_state",
                value_type="str",
                required=True,
                description="State name after the transition.",
            ),
            EventParam(
                name="trigger",
                value_type="str",
                required=True,
                description="What caused the transition (action / system / timer).",
            ),
        ),
    ),
    EventSchema(
        name="dz_form_submit",
        description="A form POST completed successfully (2xx response).",
        fires_on="htmx:afterRequest with response.status in 200..299 on [data-dz-form].",
        core_params=(
            EventParam(
                name="form_name",
                value_type="str",
                required=True,
                description="Form identifier (surface + section + field group).",
            ),
            EventParam(
                name="entity",
                value_type="str",
                required=True,
                description="Entity being created or updated.",
            ),
            EventParam(
                name="surface",
                value_type="str",
                required=True,
                description="Surface containing the form.",
            ),
        ),
        optional_params=(
            EventParam(
                name="validation_errors_count",
                value_type="int",
                description="Number of validation errors on a prior submission attempt (0 on clean submit).",
            ),
        ),
    ),
    EventSchema(
        name="dz_search",
        description="User ran a search or filter on a filterable_table.",
        fires_on="Debounced input on [data-dz-search] or htmx filter submit.",
        core_params=(
            EventParam(
                name="surface",
                value_type="str",
                required=True,
                description="Surface hosting the search.",
            ),
            EventParam(
                name="entity",
                value_type="str",
                required=True,
                description="Entity type being searched.",
            ),
            EventParam(
                name="result_count",
                value_type="int",
                required=True,
                description="Number of rows returned.",
            ),
        ),
        optional_params=(
            EventParam(
                name="query",
                value_type="str",
                description=(
                    "Search string — truncated to 100 chars. Not emitted if "
                    "the surface has any pii() fields included in the "
                    "search index."
                ),
                max_length=100,
            ),
        ),
    ),
    EventSchema(
        name="dz_api_error",
        description="An htmx request returned a 4xx/5xx response.",
        fires_on="htmx:responseError event (status >= 400).",
        core_params=(
            EventParam(
                name="status_code",
                value_type="int",
                required=True,
                description="HTTP status code.",
            ),
            EventParam(
                name="surface",
                value_type="str",
                required=True,
                description="Surface that issued the request.",
            ),
        ),
        optional_params=(
            EventParam(
                name="error_code",
                value_type="str",
                description="Application-level error code from response body (when present).",
            ),
        ),
    ),
)


_BY_NAME: dict[str, EventSchema] = {e.name: e for e in EVENT_SCHEMAS}


def get_event_schema(name: str) -> EventSchema | None:
    """Return the declared schema for an event name, or None."""
    return _BY_NAME.get(name)


def list_event_names() -> list[str]:
    """Return the sorted event-name list declared in dz/v1."""
    return sorted(_BY_NAME.keys())
