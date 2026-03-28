"""Tests for breadcrumb trail derivation."""

from dazzle_back.runtime.breadcrumbs import Crumb, build_breadcrumb_trail


class TestBuildBreadcrumbTrail:
    def test_root_path_returns_home_only(self):
        trail = build_breadcrumb_trail("/", {})
        assert len(trail) == 1
        assert trail[0].label == "Home"
        assert trail[0].url == "/"

    def test_single_segment(self):
        trail = build_breadcrumb_trail("/tasks", {})
        assert len(trail) == 2
        assert trail[0].label == "Home"
        assert trail[1].label == "Tasks"
        assert trail[1].url == "/tasks"

    def test_multi_segment(self):
        trail = build_breadcrumb_trail("/tasks/123/comments", {})
        assert len(trail) == 4
        assert trail[0].label == "Home"
        assert trail[1].label == "Tasks"
        assert trail[2].label == "123"
        assert trail[3].label == "Comments"

    def test_label_overrides(self):
        overrides = {"/tasks": "My Tasks", "/tasks/123": "Fix Bug #42"}
        trail = build_breadcrumb_trail("/tasks/123", overrides)
        assert trail[1].label == "My Tasks"
        assert trail[2].label == "Fix Bug #42"

    def test_last_crumb_has_no_url(self):
        trail = build_breadcrumb_trail("/tasks/123", {})
        assert trail[-1].url is None

    def test_empty_segments_stripped(self):
        trail = build_breadcrumb_trail("/tasks//123/", {})
        assert len(trail) == 3  # Home, Tasks, 123

    def test_crumb_dataclass_fields(self):
        crumb = Crumb(label="Test", url="/test")
        assert crumb.label == "Test"
        assert crumb.url == "/test"
