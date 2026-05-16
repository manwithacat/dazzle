"""Guided onboarding IR types (#1106 follow-up — design doc 2026-05-16).

A ``guide`` is a top-level DSL block that decorates already-mounted
surfaces with overlay / inline / checklist content. Distinct from
``experience`` (which owns its own route segment) — guides annotate
existing surfaces without taking over navigation.

v0.71.0 MVP shape — explicit-target form. A future v0.71.1 will add
the inline-annotation sugar (``onboarding step_name:`` inside a
surface action) that desugars to the same IR. The IR is identical
either way.

The load-bearing invariant is **concordance**: every step's
``complete_on`` event, ``target`` surface reference, and ``audience``
predicate must resolve against the actual DSL state. The linker
catches drift at ``dazzle validate`` time, not at runtime.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class GuideStepKind(StrEnum):
    """How a step renders on the page.

    v0.71.0 ships only IR + concordance — no runtime renderer yet.
    The kind is recorded so the runtime layer (v0.71.1+) knows what
    overlay primitive to instantiate. Single source of truth.
    """

    POPOVER = "popover"
    SPOTLIGHT = "spotlight"
    INLINE_CARD = "inline_card"
    EMPTY_STATE = "empty_state"
    BANNER = "banner"
    CHECKLIST_ITEM = "checklist_item"
    BLOCKING_TASK = "blocking_task"
    NUDGE = "nudge"


class GuideCompleteOnKind(StrEnum):
    """Which kind of trigger completes a step.

    Exactly one of these fires per step; the parser enforces
    single-value selection. The linker resolves the trigger payload
    (event ref, field path, etc.) against the DSL.
    """

    CLICK = "click"  # user clicks the targeted element
    EVENT = "event"  # an entity-lifecycle or hless event fires
    DISMISS = "dismiss"  # user explicitly dismisses the step
    FIELD_FILLED = "field_filled"  # named field acquires a non-empty value


class GuideCompleteOn(BaseModel):
    """Completion criterion for a single step.

    Exactly one of ``click``, ``event_ref``, ``dismiss``,
    ``field_filled`` is meaningful; the others default to their
    falsy value. Selected via ``kind``.
    """

    kind: GuideCompleteOnKind
    event_ref: str | None = None
    """Event reference when ``kind == EVENT``.

    Two recognised shapes:

    - ``entity.<EntityName>.<lifecycle>`` — e.g. ``entity.Task.created``.
      Lifecycle ∈ {created, updated, deleted}.
    - ``<hless_topic>.<event_name>`` — e.g.
      ``orders.OrderPlaced``. Resolves against the project's
      ``hless`` event model.
    """
    field_filled: str | None = None
    """Field path when ``kind == FIELD_FILLED``.

    Shape: ``surface.<surface_name>.field.<field_name>`` — the field
    must exist on the step's target surface; the linker enforces.
    """

    model_config = ConfigDict(frozen=True)


class GuideStep(BaseModel):
    """A single onboarding step decorating a DSL element.

    Steps are owned by guides — referenced from
    ``GuideSpec.step_order`` by their ``name``. ``target`` is the
    DSL path of the element the step decorates; the linker resolves
    it.
    """

    name: str
    """Step identifier, unique within its parent ``guide``."""

    kind: GuideStepKind

    title: str
    body: str

    target: str
    """DSL path to the decorated element.

    Recognised shapes:

    - ``surface.<surface_name>`` — whole-surface (typically used
      with ``empty_state`` or ``banner``)
    - ``surface.<surface_name>.action.<action_name>`` — a specific
      action button on a surface
    - ``surface.<surface_name>.field.<field_name>`` — a form field
    - ``surface.<surface_name>.section.<section_name>`` — a section
      within the surface body

    The linker resolves these to real IR nodes and fails the build
    if any segment doesn't match.
    """

    placement: str = "bottom"
    """Overlay positioning hint (``top`` / ``bottom`` / ``left`` /
    ``right`` / ``center``). Only meaningful for floating step kinds
    (``popover``, ``spotlight``). Static kinds (``inline_card``,
    ``empty_state``, ``banner``) ignore it.
    """

    cta_label: str | None = None
    cta_target: str | None = None
    """Optional explicit CTA pointing the user at their next surface.

    When set, ``cta_target`` must be a ``surface.<name>`` path. The
    linker also checks that the guide's audience persona has
    ``permit:`` access to that surface — pointing a non-admin user
    at an admin-only page is concordance drift.
    """

    complete_on: GuideCompleteOn

    audience_when: str | None = None
    """Optional additional audience predicate, AND-ed with the
    parent guide's audience. Reuses the predicate algebra from
    ``scope:`` rules. Lets a single guide vary which steps fire for
    which sub-personas.
    """

    model_config = ConfigDict(frozen=True)


class GuideOnComplete(BaseModel):
    """Behaviour when the last step of a guide completes."""

    emit: str | None = None
    """Optional event to emit on completion. Same resolution shape
    as ``GuideCompleteOn.event_ref`` (entity-lifecycle or
    hless topic.event)."""

    redirect: str | None = None
    """Optional ``surface.<name>`` to navigate the user to."""

    model_config = ConfigDict(frozen=True)


class GuideSpec(BaseModel):
    """Top-level guide definition — sequencing + audience + completion.

    Concordance with the surrounding DSL is enforced at link time:
    every step must resolve its target, every audience predicate
    must compile against the personas / FK graph, every completion
    event must match something the DSL emits.
    """

    name: str
    title: str
    audience: str
    """Predicate that decides whether the guide is active for the
    current user. Reuses the predicate algebra from ``scope:``
    rules — see ``project_predicate_algebra`` memory."""

    steps: list[GuideStep] = Field(default_factory=list)
    """Step definitions, owned by this guide. Steps NOT listed in
    ``step_order`` produce a linker warning (orphan)."""

    step_order: list[str] = Field(default_factory=list)
    """Linear sequence — list of step names in the order they fire.
    The linker checks every name resolves to a step in ``steps`` and
    flags duplicates."""

    on_complete: GuideOnComplete | None = None

    model_config = ConfigDict(frozen=True)


class HintDismiss(StrEnum):
    """How an inline ``hint:`` remembers user dismissal."""

    PERSIST = "persist"  # stored per-user; survives sessions
    SESSION = "session"  # cleared on logout
    NEVER = "never"  # always visible


class HintSpec(BaseModel):
    """Field-level lightweight tip primitive.

    Distinct from a full ``GuideStep``: no sequencing, no audience,
    no completion criteria. Just a body + dismiss policy. Renders
    inline alongside the decorated field as an info note.

    Reserved for one-off tips that don't warrant a guide flow.
    """

    body: str
    dismiss: HintDismiss = HintDismiss.PERSIST

    model_config = ConfigDict(frozen=True)
