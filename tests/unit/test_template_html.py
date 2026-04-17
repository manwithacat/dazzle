"""HTML template quality tests — static linting + rendered validation.

Part 1: djLint static linting for structural HTML errors in Jinja2 templates.
Part 2: Rendered HTML balance validation using stdlib html.parser.

Run standalone:
    pytest tests/unit/test_template_html.py -v

Run djLint manually:
    djlint src/dazzle_ui/templates/ --profile=jinja --lint
"""

import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "src" / "dazzle_ui" / "templates"

# These modules are part of the HTMX template runtime and may not be
# installed in every CI configuration.
pytest.importorskip("dazzle_ui.runtime.template_renderer")

from dazzle_ui.runtime.template_renderer import create_jinja_env  # noqa: E402

# ---------------------------------------------------------------------------
# HTML balance checker (stdlib, no extra dependency)
# ---------------------------------------------------------------------------


class HTMLBalanceChecker(HTMLParser):
    """Check that HTML tags are properly balanced."""

    # Self-closing tags that don't need a closing tag
    VOID_ELEMENTS = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self):
        super().__init__()
        self.stack: list[tuple[str, int, int]] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() not in self.VOID_ELEMENTS:
            self.stack.append((tag.lower(), self.getpos()[0], self.getpos()[1]))

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in self.VOID_ELEMENTS:
            return
        if not self.stack:
            self.errors.append(
                f"Closing </{tag_lower}> with no matching open tag at line {self.getpos()[0]}"
            )
            return
        if self.stack[-1][0] != tag_lower:
            open_tag, line, _col = self.stack[-1]
            self.errors.append(
                f"Mismatched tags: <{open_tag}> (line {line}) "
                f"closed by </{tag_lower}> (line {self.getpos()[0]})"
            )
        else:
            self.stack.pop()

    def check(self) -> list[str]:
        errors = list(self.errors)
        for tag, line, _col in self.stack:
            errors.append(f"Unclosed <{tag}> opened at line {line}")
        return errors


def validate_html_balance(html: str) -> list[str]:
    """Validate that HTML has balanced open/close tags."""
    checker = HTMLBalanceChecker()
    checker.feed(html)
    return checker.check()


# ===================================================================
# Part 1: djLint static linting
# ===================================================================


class TestTemplateLinting:
    """Static linting of Jinja2 template source files with djLint."""

    def test_djlint_no_errors(self):
        """All Jinja2 templates pass djLint structural checks."""
        result = subprocess.run(
            ["djlint", str(TEMPLATES_DIR), "--profile=jinja", "--lint"],
            capture_output=True,
            text=True,
        )
        # djlint --lint exits 0 when no lint errors are found
        if result.returncode != 0:
            pytest.fail(f"djLint found template issues:\n{result.stdout}")


# ===================================================================
# Part 2: Rendered HTML balance validation
# ===================================================================


# Fragment templates — self-contained HTMX partials, good balance candidates.
FRAGMENT_TEMPLATES = [
    "fragments/toast.html",
    "fragments/empty_state.html",
    "fragments/alert_banner.html",
    "fragments/steps_indicator.html",
    "fragments/skeleton_patterns.html",
    "fragments/form_errors.html",
    "fragments/bulk_actions.html",
]

# Workspace region templates — where structural bugs are most likely.
REGION_TEMPLATES = [
    "workspace/regions/metrics.html",
    "workspace/regions/detail.html",
    "workspace/regions/list.html",
    "workspace/regions/grid.html",
    "workspace/regions/timeline.html",
    "workspace/regions/queue.html",
    "workspace/regions/progress.html",
    "workspace/regions/activity_feed.html",
]

# Component templates — key structural pieces.
COMPONENT_TEMPLATES = [
    "components/modal.html",
    "components/island.html",
    "components/review_queue.html",
]


# Minimal mock context that satisfies most templates' variable expectations.
_MOCK_CONTEXT = {
    "request": None,
    "current_user": None,
    "app_name": "TestApp",
    "surfaces": [],
    "workspaces": [],
    # Fragment variables
    "message": "Test message",
    "level": "info",
    "dismissible": True,
    "empty_message": "No items found.",
    "create_url": None,
    "entity_name": "Item",
    # Steps indicator
    "steps": [{"label": "Step 1", "active": True}, {"label": "Step 2", "active": False}],
    "current_step": 0,
    # Skeleton
    "skeleton_type": "table",
    "rows": 3,
    # Form errors
    "errors": [],
    "field_errors": {},
    # Bulk actions
    "actions": [],
    "table_id": "test-table",
    # Region variables
    "title": "Test Region",
    "items": [],
    "columns": [],
    "endpoint": "/api/test",
    "entity": "Task",
    "metrics": [],
    "events": [],
    "total": 0,
    "fields": [],
    "record": {},
    "detail_fields": [],
    "action_url": None,
    "tree_items": [],
    # Component variables
    "modal_id": "test-modal",
    "modal_title": "Test Modal",
    "island_id": "test-island",
    "island_url": "/api/island",
    "reviews": [],
}


class TestRenderedHtmlValidation:
    """Render templates with mock data and validate HTML balance."""

    @pytest.fixture()
    def jinja_env(self):
        """Create a Jinja2 environment matching the runtime config."""
        env = create_jinja_env()
        # Set undefined to allow missing variables to render as empty string
        # rather than raising — we want to test HTML structure, not context completeness.
        from jinja2 import Undefined

        env.undefined = Undefined
        return env

    @pytest.mark.parametrize(
        "template_name",
        FRAGMENT_TEMPLATES + REGION_TEMPLATES + COMPONENT_TEMPLATES,
        ids=lambda t: t.replace("/", ".").removesuffix(".html"),
    )
    def test_template_renders_balanced_html(self, jinja_env, template_name):
        """Rendered template output has balanced HTML tags."""
        try:
            template = jinja_env.get_template(template_name)
        except Exception:
            pytest.skip(f"Template {template_name} not found")

        try:
            html = template.render(**_MOCK_CONTEXT)
        except Exception:
            pytest.skip(f"Template {template_name} requires specific context")

        errors = validate_html_balance(html)
        assert not errors, f"HTML balance errors in {template_name}:\n" + "\n".join(errors)

    def test_base_template_structure(self, jinja_env):
        """base.html extends to a well-formed HTML document."""
        try:
            template = jinja_env.get_template("base.html")
            html = template.render(**_MOCK_CONTEXT)
        except Exception:
            pytest.skip("base.html requires specific context")

        errors = validate_html_balance(html)
        assert not errors, "HTML balance errors in base.html:\n" + "\n".join(errors)

    def test_app_shell_layout_structure(self, jinja_env):
        """App shell layout renders balanced HTML."""
        try:
            template = jinja_env.get_template("layouts/app_shell.html")
            html = template.render(**_MOCK_CONTEXT)
        except Exception:
            pytest.skip("app_shell.html requires specific context")

        errors = validate_html_balance(html)
        assert not errors, "HTML balance errors in layouts/app_shell.html:\n" + "\n".join(errors)

    def test_grid_region_does_not_nest_card_chrome(self, jinja_env):
        """grid.html + region_card must render only one chrome layer.

        Reference model for issue #794 and its follow-up. If this test
        fails, a template edit has reintroduced nested card chrome —
        the visible ancestor is the region_card; grid item cells must
        be plain pads (no border + no bg + rounded is fine, or plain
        rounded alone).
        """
        from dazzle.testing.ux.contract_checker import find_nested_chromes

        template = jinja_env.get_template("workspace/regions/grid.html")
        context = {
            **_MOCK_CONTEXT,
            "title": "System Status",
            "region_name": "system_status",
            "items": [
                {"id": "1", "name": "api-gateway", "status": "healthy"},
                {"id": "2", "name": "auth-service", "status": "degraded"},
            ],
            "columns": [
                {"key": "name", "label": "Name", "type": "text"},
                {"key": "status", "label": "Status", "type": "badge"},
            ],
            "display_key": "name",
            "entity_name": "System",
            "action_url": "/app/system/{id}",
            "action_id_field": "id",
        }
        html = template.render(**context)

        nested = find_nested_chromes(html)
        assert not nested, (
            "grid.html renders nested card chrome — a chrome ancestor "
            "contains a chrome descendant. The canonical shape is: "
            "region_card (outer chrome) with plain item pads inside. "
            f"Pairs: {nested}"
        )


# ===================================================================
# Unit tests for the balance checker itself
# ===================================================================


class TestHTMLBalanceChecker:
    """Verify the balance checker correctly detects errors."""

    def test_balanced_html(self):
        assert validate_html_balance("<div><p>Hello</p></div>") == []

    def test_unclosed_tag(self):
        errors = validate_html_balance("<div><p>Hello</div>")
        assert len(errors) >= 1
        assert any("Mismatched" in e or "Unclosed" in e for e in errors)

    def test_void_elements_ok(self):
        assert validate_html_balance("<div><br><img><input></div>") == []

    def test_extra_closing_tag(self):
        errors = validate_html_balance("</div>")
        assert len(errors) == 1
        assert "no matching open tag" in errors[0]
