"""Validation tests for htmx wrapper types (URL, TargetSelector, HxTrigger)."""

import pytest

from dazzle.render.fragment.htmx import URL, HxTrigger, TargetSelector


def test_url_accepts_relative_path() -> None:
    u = URL("/tasks/42")
    assert str(u) == "/tasks/42"


def test_url_rejects_javascript_scheme() -> None:
    with pytest.raises(ValueError, match="scheme"):
        URL("javascript:alert(1)")


def test_url_rejects_empty_string() -> None:
    with pytest.raises(ValueError, match="empty"):
        URL("")


def test_target_selector_id_form() -> None:
    t = TargetSelector("#region-task_list-main")
    assert str(t) == "#region-task_list-main"


def test_target_selector_keyword_form() -> None:
    assert str(TargetSelector("this")) == "this"
    assert str(TargetSelector("closest tr")) == "closest tr"


def test_target_selector_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="invalid target selector"):
        TargetSelector("not a selector at all $$$")


def test_hx_trigger_simple_event() -> None:
    t = HxTrigger("click")
    assert str(t) == "click"


def test_hx_trigger_with_modifier() -> None:
    t = HxTrigger("keyup changed delay:500ms")
    assert str(t) == "keyup changed delay:500ms"


def test_hx_trigger_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        HxTrigger("")
