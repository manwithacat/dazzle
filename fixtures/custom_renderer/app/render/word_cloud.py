"""Worked example — a project-side custom renderer.

Implements the renderer protocol expected by ``dispatch_render``:

    class WordCloudRenderer:
        def render(self, surface: SurfaceLike, ctx: dict[str, Any]) -> str: ...

For `mode: custom` surfaces, ``ctx`` is sparse — the dispatcher only
populates `table` / `detail` / `form` for the corresponding modes.
Custom-mode renderers are expected to fetch their own data via the
`services` container (DB pool, repositories) or via path/query
parameters threaded into the renderer through the dispatch path.

Registration happens in ``register_with_app`` (called at app boot)
or via a startup event handler — see this directory's ``README.md``
for the wiring choices.
"""

from __future__ import annotations

import html as _html
import re
from collections import Counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.core.ir.protocols import SurfaceLike
    from dazzle.http.runtime.services import RuntimeServices


# Words too common to give signal in a small example.
_STOP_WORDS = frozenset(
    {
        "the",
        "and",
        "a",
        "an",
        "to",
        "of",
        "in",
        "is",
        "it",
        "this",
        "that",
        "for",
        "on",
        "with",
        "as",
        "but",
        "or",
        "if",
        "so",
        "be",
        "i",
        "we",
        "you",
        "they",
        "my",
        "our",
    }
)


class WordCloudRenderer:
    """A 50-line custom renderer that aggregates Feedback.body into a tag cloud.

    Demonstrates:
    - The minimal renderer-protocol shape (`render(surface, ctx) -> str`).
    - Pulling per-surface data from ``ctx`` (typed `Any` because the
      dispatcher passes a bare dict for `mode: custom`).
    - Falling back gracefully when expected ctx keys are absent — a
      custom renderer should never raise on a missing dict key; it
      should render a clearly-empty state.

    Pre-#1117 this would have been ~40 lines of code plus ~90 lines of
    monkey-patching to get the validator to accept the renderer name.
    Post-#1117, the manifest declaration + this class are enough.
    """

    def render(self, surface: SurfaceLike, ctx: dict[str, Any]) -> str:
        # `ctx` is sparse for mode: custom — defensively read.
        items = ctx.get("rows") or ctx.get("items") or []
        bodies = [str(getattr(item, "body", item.get("body", ""))) for item in items]
        if not bodies:
            return (
                '<section class="dz-section dz-section-word-cloud">'
                f"<h2>{_html.escape(surface.title or surface.name)}</h2>"
                '<p class="dz-empty">No feedback yet — leave some via the list view.</p>'
                "</section>"
            )

        counts = self._tally(bodies)
        if not counts:
            return (
                '<section class="dz-section dz-section-word-cloud">'
                f"<h2>{_html.escape(surface.title or surface.name)}</h2>"
                '<p class="dz-empty">Feedback present but no significant words.</p>'
                "</section>"
            )

        # Scale font sizes between 0.85rem and 2.5rem by frequency.
        max_count = max(counts.values())
        tags: list[str] = []
        for word, count in counts.most_common(40):
            scale = 0.85 + (count / max_count) * 1.65
            tags.append(
                f'<span class="dz-cloud-tag" '
                f'style="font-size:{scale:.2f}rem;">'
                f"{_html.escape(word)}"
                f'<sub class="dz-cloud-count">{count}</sub>'
                f"</span>"
            )

        return (
            '<section class="dz-section dz-section-word-cloud">'
            f"<h2>{_html.escape(surface.title or surface.name)}</h2>"
            '<div class="dz-cloud" role="list">' + " ".join(tags) + "</div>"
            "</section>"
        )

    @staticmethod
    def _tally(bodies: list[str]) -> Counter[str]:
        counts: Counter[str] = Counter()
        for body in bodies:
            for word in re.findall(r"[A-Za-z']{3,}", body.lower()):
                if word in _STOP_WORDS:
                    continue
                counts[word] += 1
        return counts


def register_with_app(services: RuntimeServices) -> None:
    """Wire the renderer into the app's runtime registry.

    Call this once at app boot — typically from your `app_factory` /
    custom `create_app()` after `RuntimeServices` is built, or from a
    FastAPI startup-event handler.

    For `dazzle serve`-style boots, the framework constructs services
    for you; wire this in a project-side startup hook (see this
    directory's README for the recipe).
    """
    services.renderer_registry.register(name="word_cloud", handler=WordCloudRenderer())
