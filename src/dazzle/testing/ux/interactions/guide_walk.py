"""Guide-walk oracle: prove a guide's overlay actually renders for its audience.

Scope A (the shipped first slice): for each guide, fetch the FIRST step's target
surface as the guide's audience persona and assert the ``<dz-onboarding-step>``
overlay renders there — the runtime proof that the persona, where they land, is
actually shown the guide the DSL promises. First steps are list/create surfaces
(deterministic URLs); a first step that targets a detail/edit surface is
log-skipped (it needs a seeded record id — deferred to a future full-journey
walk), never silently dropped.

Server-rendered HTML, so this uses a plain sync HTTP client (``.get(path)`` /
``.post(path)``) rather than Playwright. It implements the ``Interaction``
protocol (``name`` + ``execute(page)``); ``page`` is ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dazzle.testing.ux.interactions.base import InteractionResult


def _surface_by_name(target: str, surfaces: list[Any]) -> Any | None:
    """Resolve a guide target (``surface.<name>[...]``) to its SurfaceSpec."""
    name = target.removeprefix("surface.").split(".")[0]
    return next((s for s in surfaces if getattr(s, "name", None) == name), None)


def _surface_url(surface: Any) -> tuple[str | None, str]:
    """Map a SurfaceSpec to its runtime URL + a normalised mode string.

    Returns ``(url, mode)``. ``url`` is ``None`` for detail/edit/view/custom
    surfaces (they need a record id — not walkable in scope A).
    """
    entity = getattr(surface, "entity_ref", None)
    raw_mode = getattr(surface, "mode", None)
    mode = getattr(raw_mode, "value", str(raw_mode)).lower()
    if not entity:
        return None, mode
    slug = entity.lower()
    if "list" in mode:
        return f"/app/{slug}", mode
    if "create" in mode:
        return f"/app/{slug}/create", mode
    return None, mode  # view / edit / custom — needs a record id


@dataclass
class GuideWalkInteraction:
    """Assert a guide's first-step overlay renders for its audience persona."""

    guide: Any
    persona: str
    surfaces: list[Any]
    http: Any  # sync client exposing .get(path) and .post(path)
    name: str = field(default="")

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"guide-walk:{self.persona}:{self.guide.name}"

    def execute(self, page: Any = None) -> InteractionResult:  # noqa: ANN401, ARG002
        if not self.guide.step_order:
            return InteractionResult(self.name, False, "guide has no step_order")
        first_name = self.guide.step_order[0]
        steps = {s.name: s for s in self.guide.steps}
        step = steps.get(first_name)
        if step is None:
            return InteractionResult(
                self.name, False, f"step_order names unknown step {first_name!r}"
            )

        surface = _surface_by_name(step.target, self.surfaces)
        if surface is None:
            return InteractionResult(
                self.name, False, f"could not resolve target {step.target!r} to a surface"
            )
        url, mode = _surface_url(surface)
        if url is None:
            # Honest skip — not walkable in scope A. Passes (no false failure)
            # but the reason records exactly what wasn't tested.
            return InteractionResult(
                self.name,
                True,
                f"skipped: first step targets a {mode!r} surface ({step.target}) — "
                f"needs a record id; deferred to the full-journey walk",
                {"skipped": True, "mode": mode},
            )

        resp = self.http.get(url)
        if resp.status_code != 200:
            return InteractionResult(
                self.name, False, f"{url} returned {resp.status_code} for persona {self.persona!r}"
            )

        html = resp.text
        # Attribute order is NOT guaranteed — the real tag is
        # `<dz-onboarding-step class="..." data-guide="..." data-step="..." ...>`.
        # Match the identifying attributes independently.
        if (
            "dz-onboarding-step" not in html
            or f'data-guide="{self.guide.name}"' not in html
            or f'data-step="{first_name}"' not in html
        ):
            return InteractionResult(
                self.name,
                False,
                f"overlay for {self.guide.name}/{first_name} did NOT render on {url} as {self.persona!r} "
                f"— the guide promises it but the runtime didn't show it",
                {"url": url},
            )

        return InteractionResult(
            self.name,
            True,
            f"overlay rendered on {url} for {self.persona!r}",
            {"url": url, "mode": mode},
        )
