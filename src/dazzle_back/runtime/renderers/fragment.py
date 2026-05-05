"""Fragment renderer adapter — re-exports `dazzle.render.fragment.renderer.FragmentRenderer`.

Stable adapter import for the registration site, even if the underlying
renderer package reorganises later. Today this is a trivial re-export.
"""

from dazzle.render.fragment.renderer import FragmentRenderer

__all__ = ["FragmentRenderer"]
