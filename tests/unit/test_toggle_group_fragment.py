"""Cycle 242 — toggle-group (segmented control) fragment contract (UX-046).

Final cycle of the component menagerie mini-arc (238-242). Verifies the
canonical anatomy, design-token compliance, hidden-input synchronisation,
keyboard accessibility, and ARIA semantics of
``fragments/toggle_group.html``.
"""

import pytest

pytest.importorskip("dazzle_ui", reason="dazzle_ui not installed")


class TestToggleGroupFragment:
    """Segmented-control toggle group renders the canonical anatomy."""

    def _render(self, **ctx) -> str:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        tmpl = env.get_template("fragments/toggle_group.html")
        return tmpl.render(**ctx)

    def _default_options(self):
        return [
            {"value": "list", "label": "List"},
            {"value": "grid", "label": "Grid"},
            {"value": "kanban", "label": "Kanban"},
        ]

    def test_renders_canonical_markers(self) -> None:
        html = self._render(name="view", options=self._default_options())
        # Outer container markers
        assert "dz-toggle-group" in html
        assert 'x-data="dzToggleGroup"' in html
        assert 'data-dz-multi="false"' in html
        # Hidden input for form submission
        assert '<input type="hidden" name="view"' in html
        # Per-button markers
        assert html.count("data-dz-toggle-item") == 3
        assert 'data-dz-value="list"' in html
        assert 'data-dz-value="grid"' in html
        assert 'data-dz-value="kanban"' in html

    def test_exclusive_uses_radiogroup_role(self) -> None:
        html = self._render(name="view", options=self._default_options())
        assert 'role="radiogroup"' in html
        # aria-label defaults to name
        assert 'aria-label="view"' in html

    def test_multi_uses_group_role(self) -> None:
        html = self._render(name="filters", options=self._default_options(), multi=True)
        assert 'role="group"' in html
        assert 'data-dz-multi="true"' in html

    def test_uses_design_tokens_not_daisyui(self) -> None:
        """Gate 2: zero DaisyUI class names + uses semantic CSS classes.

        v0.62 CSS refactor: container/item chrome moved from inline
        Tailwind to .dz-toggle-group / .dz-toggle-item rules in
        components/fragments.css."""
        html = self._render(name="view", options=self._default_options())
        # Semantic classes in template
        assert "dz-toggle-group" in html
        assert "dz-toggle-item" in html
        # Legacy DaisyUI classes MUST NOT appear
        assert '"join"' not in html and " join " not in html
        assert "join-item" not in html
        assert "btn-primary" not in html
        assert "btn-ghost" not in html
        assert "btn-sm" not in html
        # The standalone `btn` class (as opposed to class="btn-...") must not
        # appear as a word-boundary match
        import re

        assert not re.search(r'class="[^"]*\bbtn\b[^-]', html)

        # CSS rule carries border + bg tint
        from pathlib import Path

        css = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/runtime/static/css/components/fragments.css"
        ).read_text()
        group_block = css.split(".dz-toggle-group {")[1].split("}")[0]
        assert "border: 1px solid var(--colour-border)" in group_block

    def test_label_override(self) -> None:
        html = self._render(
            name="view",
            options=self._default_options(),
            label="Choose view mode",
        )
        assert 'aria-label="Choose view mode"' in html

    def test_initial_value_populates_data_attribute(self) -> None:
        html = self._render(
            name="view",
            options=self._default_options(),
            initial="grid",
        )
        assert 'data-dz-value="grid"' in html

    def test_no_initial_value_omits_data_attribute(self) -> None:
        html = self._render(name="view", options=self._default_options())
        # The outer container's opening tag should NOT carry a data-dz-value
        # attribute when no `initial` was provided. (Per-option buttons still
        # carry their own data-dz-value markers; those are inside <button>
        # elements further down and don't belong on the container.)
        outer_open = html[html.find("<div") : html.find(">", html.find("<div")) + 1]
        assert "data-dz-value" not in outer_open

    def test_keyboard_navigation_handlers(self) -> None:
        """Gate 4: Left and Right arrow keys move focus between buttons."""
        html = self._render(name="view", options=self._default_options())
        assert "@keydown.left.prevent" in html
        assert "@keydown.right.prevent" in html

    def test_focus_visible_ring_present(self) -> None:
        """Gate 4: keyboard focus ring via focus-visible (not focus).

        v0.62 CSS refactor: focus-visible chrome lives on the
        `.dz-toggle-item:focus-visible` rule rather than inline
        `focus-visible:ring-1 focus-visible:ring-[hsl(var(--ring))]`
        Tailwind. The intent — show the ring on keyboard focus only,
        not mouse click — is preserved by using :focus-visible rather
        than :focus."""
        from pathlib import Path

        css = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/runtime/static/css/components/fragments.css"
        ).read_text()
        # The :focus-visible variant must exist
        assert ".dz-toggle-item:focus-visible {" in css
        # And must NOT be a plain :focus rule (that would show on click)
        assert ".dz-toggle-item:focus {" not in css

        focus_block = css.split(".dz-toggle-item:focus-visible {")[1].split("}")[0]
        # Ring colour comes from the brand token
        assert "var(--colour-brand)" in focus_block

    def test_aria_pressed_per_button(self) -> None:
        """Gate 1: aria-pressed is reactive on every button."""
        html = self._render(name="view", options=self._default_options())
        # Three buttons, three :aria-pressed bindings
        assert html.count(":aria-pressed=") == 3

    def test_hidden_input_sync_binding(self) -> None:
        """Gate 3: hidden input value tracks Alpine state."""
        html = self._render(name="scope", options=[{"value": "a", "label": "A"}])
        # The Alpine :value= binding joins multi-values with commas
        assert ':value="multi ? (value || []).join' in html

    def test_button_count_matches_options(self) -> None:
        """Arbitrary option lists produce the right button count."""
        options = [{"value": f"opt{i}", "label": f"Opt {i}"} for i in range(5)]
        html = self._render(name="pick", options=options)
        assert html.count("data-dz-toggle-item") == 5
        for i in range(5):
            assert f'data-dz-value="opt{i}"' in html

    def test_option_labels_are_autoescaped(self) -> None:
        """Option labels pass through Jinja autoescape — no XSS vector."""
        dangerous_options = [
            {"value": "a", "label": "<script>alert('xss')</script>"},
        ]
        html = self._render(name="pick", options=dangerous_options)
        # Raw <script> tag must not appear
        assert "<script>alert" not in html
        # Escaped form must appear
        assert "&lt;script&gt;" in html or "&lt;" in html
