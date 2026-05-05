"""FragmentRenderer — emits HTML from Fragment trees.

Single-class renderer. The `render` method match-dispatches on the Fragment
union; per-primitive emit methods produce HTML strings. The match block is
the runtime exhaustiveness check — adding a new primitive without adding a
match arm causes mypy to flag the unreachable case (with `--strict`) and
the test_fragment_exhaustiveness test (Task 24) to fail.
"""

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.errors import FragmentError
from dazzle.render.fragment.escape import RawHTML, Slot
from dazzle.render.fragment.primitives import Fragment, Heading, Text


class FragmentRenderer:
    """Emit HTML from a Fragment tree.

    Stateless — a single instance can be reused across requests. The
    RenderContext is per-render-call and threads tokens through descent.
    """

    def render(self, fragment: Fragment, ctx: RenderContext | None = None) -> str:
        ctx = ctx if ctx is not None else RenderContext()
        return self._emit(fragment, ctx)

    def _emit(self, fragment: Fragment, ctx: RenderContext) -> str:
        match fragment:
            # Escape hatches first — most likely path is RawHTML interop
            case RawHTML(html=html):
                return html
            case Slot(name=name):
                raise FragmentError(
                    f"unfilled slot {name!r} reached the renderer; "
                    f"slots must be substituted before render() is called"
                )
            # Content
            case Text():
                return self._emit_text(fragment, ctx)
            case Heading():
                return self._emit_heading(fragment, ctx)
            # Subsequent tasks (18-23) extend the match block.
            case _:
                raise FragmentError(
                    f"renderer has no emit for {type(fragment).__name__!r} yet — "
                    f"add a match arm in FragmentRenderer._emit"
                )

    # --- per-primitive emitters ---

    def _emit_text(self, t: Text, ctx: RenderContext) -> str:
        body = ctx.escape(t.body)
        cls = f"dz-text dz-text--tone-{t.tone}"
        return f'<span class="{cls}">{body}</span>'

    def _emit_heading(self, h: Heading, ctx: RenderContext) -> str:
        body = ctx.escape(h.body)
        cls = f"dz-heading dz-heading--level-{h.level}"
        return f'<h{h.level} class="{cls}">{body}</h{h.level}>'
