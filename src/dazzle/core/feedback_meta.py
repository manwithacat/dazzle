"""Feedback-widget page contract: the ``<meta>`` names and their builder (#1854).

A ``core`` leaf so the page layer (``page.runtime.app_chrome`` emits the
metas) and the render layer (``render.dispatch`` reads
``dz-feedback-review-personas`` back to stamp ``dz-feedback-review``) share
one definition without ``render`` importing ``page`` (ADR-0038).
"""

from __future__ import annotations

from typing import Any

from dazzle.core.ir.feedback_widget import (
    DEFAULT_FEEDBACK_CATEGORIES,
    DEFAULT_FEEDBACK_SEVERITIES,
)

FEEDBACK_META_SHORTCUT = "dz-feedback-shortcut"
FEEDBACK_META_CATEGORIES = "dz-feedback-categories"
FEEDBACK_META_SEVERITIES = "dz-feedback-severities"
FEEDBACK_META_SCREENSHOT = "dz-feedback-screenshot"
FEEDBACK_META_REVIEW_SHORTCUT = "dz-feedback-review-shortcut"
FEEDBACK_META_REVIEW_PERSONAS = "dz-feedback-review-personas"
#: Per-request: ``1`` when the signed-in user is a review persona (dispatch).
FEEDBACK_META_REVIEW = "dz-feedback-review"


def feedback_policy_meta(feedback_widget: Any) -> list[tuple[str, str]]:
    """The policy metas for a mounted feedback widget (#1854).

    ``dz-feedback-categories`` / ``dz-feedback-severities`` are comma lists in
    DSL order (the first severity is the default), ``dz-feedback-screenshot``
    is ``off`` | ``optional``, ``dz-feedback-review-shortcut`` is the review
    chord or ``none`` and ``dz-feedback-review-personas`` the comma list of
    reviewer personas (absent when the DSL declares no ``review:``).
    """
    review = getattr(feedback_widget, "review", None)
    categories = getattr(feedback_widget, "categories", None) or DEFAULT_FEEDBACK_CATEGORIES
    severities = getattr(feedback_widget, "severities", None) or DEFAULT_FEEDBACK_SEVERITIES
    out: list[tuple[str, str]] = [
        (FEEDBACK_META_CATEGORIES, ",".join(str(c) for c in categories)),
        (FEEDBACK_META_SEVERITIES, ",".join(str(s) for s in severities)),
        (FEEDBACK_META_SCREENSHOT, str(getattr(review, "screenshot", "") or "off")),
        (FEEDBACK_META_REVIEW_SHORTCUT, str(getattr(review, "shortcut", "") or "none")),
    ]
    personas = [str(p) for p in (getattr(review, "personas", None) or []) if p]
    if personas:
        out.append((FEEDBACK_META_REVIEW_PERSONAS, ",".join(personas)))
    return out
