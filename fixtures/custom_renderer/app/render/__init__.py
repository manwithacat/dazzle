"""Project-side renderers for the custom_renderer example.

Two renderers ship here, demonstrating the two reasons to register one:

- ``word_cloud`` — a ``mode: custom`` surface that fetches its own data
  and renders something the built-in modes don't cover (`word_cloud.py`).
- ``feedback_detail`` — a per-entity *detail viewer* on a ``mode: view``
  surface that delegates to the framework's generic detail rendering and
  wraps it with bespoke chrome (`feedback_detail.py`, #1297).

``register_all`` wires both into the runtime registry. Call it once at
app boot — see this directory's README for the attachment-point choices
(FastAPI startup event vs custom app factory).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.render.feedback_detail import register_with_app as register_feedback_detail
from app.render.word_cloud import register_with_app as register_word_cloud

if TYPE_CHECKING:
    from dazzle.http.runtime.services import RuntimeServices


def register_all(services: RuntimeServices) -> None:
    """Register every project-side renderer in one call."""
    register_word_cloud(services)
    register_feedback_detail(services)


__all__ = ["register_all"]
