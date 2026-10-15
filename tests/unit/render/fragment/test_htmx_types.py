"""Validation tests for htmx wrapper types (URL, TargetSelector, HxTrigger)."""

import pytest

from dazzle.render.fragment.htmx import URL, HxTrigger, TargetSelector


@pytest.mark.parametrize(
    ("cls", "value"),
    [
        pytest.param(URL, "/tasks/42", id="url.relative_path"),
        pytest.param(URL, "https://example.com/api", id="url.https_absolute"),
        pytest.param(URL, "mailto:nobody@example.com", id="url.mailto"),
        pytest.param(TargetSelector, "#region-task_list-main", id="target.id"),
        pytest.param(TargetSelector, ".dz-card", id="target.class"),
        pytest.param(TargetSelector, "this", id="target.keyword_this"),
        pytest.param(TargetSelector, "closest tr", id="target.closest_tag"),
        pytest.param(TargetSelector, "closest .dz-card", id="target.closest_class"),
        pytest.param(TargetSelector, "closest #region-x", id="target.closest_id"),
        pytest.param(TargetSelector, "find .dz-button", id="target.find_class"),
        pytest.param(HxTrigger, "click", id="trigger.simple_event"),
        pytest.param(HxTrigger, "keyup changed delay:500ms", id="trigger.with_modifiers"),
    ],
)
def test_accepts_and_round_trips(cls: type, value: str) -> None:
    """Valid values are accepted and render back unchanged."""
    assert str(cls(value)) == value


@pytest.mark.parametrize(
    ("cls", "value", "match"),
    [
        pytest.param(URL, "", "empty", id="url.empty"),
        pytest.param(URL, "javascript:alert(1)", "scheme", id="url.javascript"),
        # Case-insensitive: JAVASCRIPT: is the same vector as javascript:.
        pytest.param(URL, "JAVASCRIPT:alert(1)", "scheme", id="url.javascript_uppercase"),
        pytest.param(URL, "data:text/html,<script>alert(1)</script>", "scheme", id="url.data"),
        pytest.param(URL, "vbscript:msgbox(1)", "scheme", id="url.vbscript"),
        pytest.param(URL, "file:///etc/passwd", "scheme", id="url.file"),
        # Browsers tolerate leading whitespace in attributes; we don't.
        pytest.param(URL, "\tjavascript:alert(1)", "whitespace", id="url.leading_whitespace"),
        pytest.param(
            TargetSelector,
            "not a selector at all $$$",
            "invalid target selector",
            id="target.garbage",
        ),
        pytest.param(HxTrigger, "", "empty", id="trigger.empty"),
        pytest.param(HxTrigger, "   ", "empty or whitespace", id="trigger.whitespace_only"),
    ],
)
def test_rejects(cls: type, value: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        cls(value)
