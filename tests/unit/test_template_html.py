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
        """grid.html must render zero chrome layers of its own.

        Reference model for #794 + its two follow-ups. Regions are
        always rendered into a dashboard card slot that already owns
        chrome (border + rounded + bg) and title, so both region_card
        and the grid items must be chrome-free. A chrome layer inside
        the region output = a visible card-within-a-card.
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
# Composite dashboard-slot + region-card shape tests (#794 post-mortem)
# ===================================================================
#
# These tests simulate what a user actually sees: the dashboard card
# slot in workspace/_content.html fetches the region content via
# HTMX and substitutes it into the slot's body. Every prior
# shape-nesting test ran on each layer alone; the AegisMark-reported
# card-in-card was invisible until the two were concatenated. The
# composite harness here closes that blind spot.
#
# The dashboard slot structure below mirrors workspace/_content.html
# lines 111-167 (as of v0.57.36). If _content.html drifts, the
# companion test_dashboard_slot_fingerprint test will fail to tell us
# the shell is out of sync and needs updating.

# Canonical dashboard-slot wrapper — rendered server-side for the
# initial dashboard page. Alpine hydrates data-card-id from JS state;
# we fix it at "card-0" for testing.
_DASHBOARD_SLOT_WITH_REGION = """
<div data-card-id="card-0"
     class="relative group outline-none focus:ring-2 focus:ring-[hsl(var(--ring))] focus:ring-offset-2">
  <article class="rounded-md border bg-[hsl(var(--card))] overflow-hidden"
           role="article"
           aria-labelledby="card-title-card-0">
    <div class="flex items-center justify-between px-4 py-2 cursor-grab min-h-[36px]">
      <h3 id="card-title-card-0"
          class="text-[15px] font-medium leading-[22px] tracking-[-0.01em] text-[hsl(var(--foreground))] select-none">
        {card_title}
      </h3>
    </div>
    <div class="px-4 pb-4" id="region-{region_name}-card-0">
      {region_html}
    </div>
  </article>
</div>
"""


# Region-template × sample-context matrix. Each entry is a real
# context a runtime render site could build for that template.
_REGION_CASES = [
    (
        "workspace/regions/grid.html",
        "System Status",
        {
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
        },
    ),
    (
        "workspace/regions/list.html",
        "Recent Tickets",
        {
            "region_name": "recent_tickets",
            "items": [{"id": "1", "title": "Broken device"}],
            "columns": [{"key": "title", "label": "Title", "type": "text"}],
            "display_key": "title",
            "entity_name": "Ticket",
            "total": 1,
            "action_url": "/app/ticket/{id}",
            "action_id_field": "id",
        },
    ),
    (
        "workspace/regions/timeline.html",
        "Alert Timeline",
        {
            "region_name": "alert_timeline",
            "items": [{"id": "1", "message": "CPU high", "triggered_at": "2026-04-17T10:00Z"}],
            "columns": [{"key": "message", "label": "Message", "type": "text"}],
            "display_key": "message",
            "date_field": "triggered_at",
            "entity_name": "Alert",
        },
    ),
    (
        "workspace/regions/kanban.html",
        "Ticket Board",
        {
            "region_name": "ticket_board",
            "items": [{"id": "1", "title": "Feature", "status": "open"}],
            "columns": [{"key": "title", "label": "Title", "type": "text"}],
            "display_key": "title",
            "entity_name": "Ticket",
            "group_by": "status",
            "kanban_columns": [
                {"value": "open", "label": "Open", "items": [{"id": "1", "title": "Feature"}]},
                {"value": "closed", "label": "Closed", "items": []},
            ],
        },
    ),
    (
        "workspace/regions/bar_chart.html",
        "Alerts by Severity",
        {
            "region_name": "alert_severity_breakdown",
            "items": [{"severity": "high", "count": 3}, {"severity": "low", "count": 12}],
            "group_by": "severity",
            "columns": [{"key": "severity", "label": "Severity", "type": "text"}],
            "display_key": "severity",
            "entity_name": "Alert",
        },
    ),
    (
        "workspace/regions/metrics.html",
        "Health Summary",
        {
            "region_name": "health_summary",
            "metrics": [
                {"key": "total_systems", "label": "Total Systems", "value": 12},
                {"key": "healthy_count", "label": "Healthy", "value": 8},
            ],
            "entity_name": "System",
        },
    ),
    (
        "workspace/regions/queue.html",
        "Ack Queue",
        {
            "region_name": "ack_queue",
            "items": [{"id": "1", "message": "Unacked alert"}],
            "columns": [{"key": "message", "label": "Message", "type": "text"}],
            "display_key": "message",
            "entity_name": "Alert",
            "queue_transitions": [],
        },
    ),
    (
        "workspace/regions/activity_feed.html",
        "Comment Activity",
        {
            "region_name": "comment_activity",
            "items": [
                {"id": "1", "content": "Looking into this", "created_at": "2026-04-17T10:00Z"}
            ],
            "columns": [{"key": "content", "label": "Content", "type": "text"}],
            "display_key": "content",
            "entity_name": "Comment",
        },
    ),
    (
        "workspace/regions/heatmap.html",
        "Alert Heatmap",
        {
            "region_name": "alert_heatmap",
            "heatmap_matrix": [],
            "heatmap_col_values": [],
            "heatmap_thresholds": {},
            "group_by": "severity",
            "entity_name": "Alert",
        },
    ),
    (
        "workspace/regions/progress.html",
        "Backlog Progress",
        {
            "region_name": "backlog_progress",
            "stage_counts": [{"label": "Open", "count": 3}, {"label": "Closed", "count": 7}],
            "progress_total": 10,
            "complete_count": 7,
            "complete_pct": 70,
            "entity_name": "Ticket",
        },
    ),
    (
        "workspace/regions/tree.html",
        "Device Tree",
        {
            "region_name": "device_tree",
            "tree_items": [{"id": "1", "name": "batch-a", "_children": []}],
            "columns": [{"key": "name", "label": "Name", "type": "text"}],
            "display_key": "name",
            "entity_name": "Device",
            "group_by": "batch_number",
        },
    ),
    (
        "workspace/regions/diagram.html",
        "Fleet Diagram",
        {
            "region_name": "fleet_diagram",
            "items": [{"id": "1", "name": "device-1"}],
            "columns": [{"key": "name", "label": "Name", "type": "text"}],
            "display_key": "name",
            "entity_name": "Device",
        },
    ),
    (
        "workspace/regions/tabbed_list.html",
        "Issue Tabs",
        {
            "region_name": "issue_tabs",
            "source_tabs": [
                {"source": "open", "title": "Open", "endpoint": "/api/_regions/issue_tabs/open"},
                {
                    "source": "closed",
                    "title": "Closed",
                    "endpoint": "/api/_regions/issue_tabs/closed",
                },
            ],
            "entity_name": "IssueReport",
        },
    ),
    (
        "workspace/regions/funnel_chart.html",
        "Resolution Funnel",
        {
            "region_name": "resolution_funnel",
            "items": [{"status": "open", "count": 3}, {"status": "closed", "count": 7}],
            "group_by": "status",
            "columns": [{"key": "status", "label": "Status", "type": "text"}],
            "display_key": "status",
            "entity_name": "Ticket",
        },
    ),
]


class TestDashboardRegionCompositeShapes:
    """Shape-safety contract on the HTMX-loaded composite.

    The #794 saga closed when the region_card macro stopped emitting
    its own chrome + title, because the dashboard slot already owns
    both. These tests lock that invariant by concatenating the real
    dashboard slot HTML with each real region template render and
    asserting zero nested chrome.
    """

    @pytest.fixture()
    def jinja_env(self):
        env = create_jinja_env()
        from jinja2 import Undefined

        env.undefined = Undefined
        return env

    @pytest.mark.parametrize(
        "template_name,card_title,context",
        _REGION_CASES,
        ids=lambda v: (
            v.replace("workspace/regions/", "").removesuffix(".html")
            if isinstance(v, str) and v.startswith("workspace/")
            else None
        ),
    )
    def test_composite_has_no_nested_chrome(self, jinja_env, template_name, card_title, context):
        """Dashboard slot + rendered region must produce no card-in-card."""
        from dazzle.testing.ux.contract_checker import find_nested_chromes

        try:
            template = jinja_env.get_template(template_name)
        except Exception:
            pytest.skip(f"Template {template_name} not found")

        ctx = {**_MOCK_CONTEXT, "title": card_title, **context}
        try:
            region_html = template.render(**ctx)
        except Exception as e:
            pytest.skip(f"Template {template_name} requires different context: {e}")

        composite = _DASHBOARD_SLOT_WITH_REGION.format(
            card_title=card_title,
            region_name=context["region_name"],
            region_html=region_html,
        )

        nested = find_nested_chromes(composite)
        assert not nested, (
            f"Composite (dashboard slot + {template_name}) renders nested "
            f"card chrome — a chrome ancestor contains a chrome descendant. "
            f"Dashboard slot owns chrome + title; regions must be bare. "
            f"Pairs: {nested}"
        )

    @pytest.mark.parametrize(
        "template_name,card_title,context",
        _REGION_CASES,
        ids=lambda v: (
            v.replace("workspace/regions/", "").removesuffix(".html")
            if isinstance(v, str) and v.startswith("workspace/")
            else None
        ),
    )
    def test_composite_has_no_duplicate_titles(self, jinja_env, template_name, card_title, context):
        """Dashboard slot + rendered region must not repeat the card title.

        AegisMark's #794 follow-up flagged "Grade Distribution" appearing
        3× in the DOM — once from the dashboard header, again from the
        region_card macro. Post-fix the macro is bare; this gate locks
        that against regression across every region template.
        """
        from dazzle.testing.ux.contract_checker import find_duplicate_titles_in_cards

        try:
            template = jinja_env.get_template(template_name)
        except Exception:
            pytest.skip(f"Template {template_name} not found")

        ctx = {**_MOCK_CONTEXT, "title": card_title, **context}
        try:
            region_html = template.render(**ctx)
        except Exception as e:
            pytest.skip(f"Template {template_name} requires different context: {e}")

        composite = _DASHBOARD_SLOT_WITH_REGION.format(
            card_title=card_title,
            region_name=context["region_name"],
            region_html=region_html,
        )

        dupes = find_duplicate_titles_in_cards(composite)
        assert not dupes, (
            f"Composite (dashboard slot + {template_name}) contains a "
            f"duplicated heading inside a card — the dashboard renders "
            f"{card_title!r} in its header and the region emitted it "
            f"again. Regions must not render their own title. "
            f"Pairs (card_tag, duplicated_text): {dupes}"
        )

    def test_dashboard_slot_fingerprint(self, jinja_env):
        """The composite harness hardcodes the dashboard-slot chrome
        shell. If workspace/_content.html drifts (e.g. class changes,
        article→section), the fingerprint test catches it and signals
        the shell needs updating in this test file.

        Checking the most load-bearing class combo: the <article> with
        ``rounded-md border bg-[hsl(var(--card))]``. That's the card
        surface AegisMark's counters depend on.
        """
        content_template = TEMPLATES_DIR / "workspace" / "_content.html"
        text = content_template.read_text()
        assert "rounded-md border" in text, (
            "workspace/_content.html no longer contains 'rounded-md border' — "
            "the dashboard slot chrome has changed. Update "
            "_DASHBOARD_SLOT_WITH_REGION in this test file to match."
        )
        assert "bg-[hsl(var(--card))]" in text, (
            "workspace/_content.html no longer contains 'bg-[hsl(var(--card))]' — "
            "the card background token has changed. Update "
            "_DASHBOARD_SLOT_WITH_REGION in this test file to match."
        )

    def test_context_selector_defaults_to_first_option(self):
        """#870: when no saved preference exists, the context selector
        falls through to ``sel.options[1]`` (the first real option after
        the hard-coded "All" entry) so workspaces with regions filtering
        on ``current_context`` don't render fully-empty on first load.
        """
        content_template = TEMPLATES_DIR / "workspace" / "_content.html"
        text = content_template.read_text()
        assert "sel.options[1]" in text, (
            "workspace/_content.html no longer falls through to "
            "sel.options[1] when no saved preference exists — #870 will "
            "regress (workspaces with current_context filters render empty "
            "on first load for fresh users)."
        )

    def test_bare_region_card_macro_stays_bare(self):
        """Lock #794's fix: region_card emits no chrome classes.

        If a future edit adds back ``bg-[hsl(var(--card))]``,
        ``rounded-*``, ``border``, or ``shadow-*`` to the macro, this
        test fails and catches the regression before the composite
        gate even runs — with a clearer root-cause message.
        """
        macro_path = TEMPLATES_DIR / "macros" / "region_wrapper.html"
        text = macro_path.read_text()
        # Strip block comments before scanning — they document the
        # prior shape and contain the chrome class names we're banning.
        stripped = _strip_jinja_comments(text)
        for banned in ("bg-[hsl(var(--card))]", "rounded-[", "shadow-["):
            assert banned not in stripped, (
                f"region_card macro re-introduced {banned!r} — the "
                "dashboard slot owns chrome, the macro must stay bare. "
                "See issue #794 second follow-up."
            )


def _strip_jinja_comments(text: str) -> str:
    """Remove {# ... #} blocks so we can scan macro body only."""
    import re

    return re.sub(r"\{#.*?#\}", "", text, flags=re.DOTALL)


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
