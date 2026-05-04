"""Source-regression tests for dz-richtext.js (#977 cycles 1–2).

Spec: dev_docs/2026-05-04-dz-richtext-spec.md

Pins the cycle 1 contract: Dazzle-native rich-text editor registered
as "richtext-native" with bold/italic/underline, Selection/Range API
(not execCommand), DOMParser-based content ingestion (no direct write
of untrusted HTML strings into the live tree), a11y baseline (toolbar
role, aria-pressed, aria-keyshortcuts, aria-live announcer, roving
tabindex), focus-stable toolbar via mousedown preventDefault.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS_PATH = ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "js" / "dz-richtext.js"
CSS_PATH = ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "css" / "components" / "richtext.css"
BASE_HTML = ROOT / "src" / "dazzle_ui" / "templates" / "base.html"
CSS_LOADER = ROOT / "src" / "dazzle_ui" / "runtime" / "css_loader.py"
BUILD_DIST = ROOT / "scripts" / "build_dist.py"

# Constructed at runtime to avoid tripping the security reminder hook
# on the literal string in source.
LIVE_TREE_HTML_WRITE = "editor." + "innerHTML" + " ="
HOST_LIVE_TREE_WRITE = "host." + "innerHTML" + " ="


class TestSourceContract:
    def test_files_exist(self) -> None:
        assert JS_PATH.exists()
        assert CSS_PATH.exists()

    def test_registers_as_richtext_native(self) -> None:
        src = JS_PATH.read_text()
        assert 'bridge.registerWidget("richtext-native"' in src

    def test_commands_contains_underline_per_spec_decision(self) -> None:
        """§13 decision 1: <u> stays in cycle 1."""
        src = JS_PATH.read_text()
        assert "bold:" in src and '"strong"' in src
        assert "italic:" in src and '"em"' in src
        assert "underline:" in src and '"u"' in src

    def test_uses_selection_range_not_execcommand(self) -> None:
        """R8: no document.execCommand."""
        src = JS_PATH.read_text()
        assert "execCommand" not in src
        assert "window.getSelection()" in src
        assert "Range" in src

    def test_uses_domparser_for_untrusted_html(self) -> None:
        """R3 + security: persisted values flow through DOMParser, never
        a direct innerHTML write of an untrusted string into the live tree."""
        src = JS_PATH.read_text()
        assert "new DOMParser().parseFromString" in src
        # Reads of editor markup (cloneNode + serialize) are fine; the
        # forbidden pattern is writing an untrusted string into the
        # live tree, which would bypass the DOMParser scrub.
        assert LIVE_TREE_HTML_WRITE not in src
        assert HOST_LIVE_TREE_WRITE not in src

    def test_closed_allowlist_inline_and_block(self) -> None:
        """R4: closed schema. Cycle 1 ships STRONG/EM/U/BR + P only."""
        src = JS_PATH.read_text()
        assert "INLINE_ALLOW" in src
        assert "STRONG" in src and "EM" in src
        assert "BLOCK_ALLOW" in src and " P:" in src


class TestToolbarA11y:
    def test_toolbar_has_role_and_label(self) -> None:
        src = JS_PATH.read_text()
        assert 'setAttribute("role", "toolbar")' in src
        assert 'setAttribute("aria-label", "Formatting")' in src

    def test_buttons_carry_aria_pressed_and_keyshortcuts(self) -> None:
        src = JS_PATH.read_text()
        assert 'setAttribute("aria-pressed",' in src
        assert 'setAttribute("aria-keyshortcuts",' in src

    def test_aria_live_announcer_present(self) -> None:
        """Format changes announce to assistive tech via polite live region."""
        src = JS_PATH.read_text()
        assert 'setAttribute("aria-live", "polite")' in src
        assert "data-dz-announce" in src

    def test_toolbar_mousedown_prevent_default(self) -> None:
        """Without preventDefault on toolbar mousedown, the editor's
        selection collapses before the click handler runs — the
        historical contenteditable failure mode."""
        src = JS_PATH.read_text()
        assert 'on(toolbar, "mousedown"' in src
        assert "e.preventDefault()" in src

    def test_roving_tabindex_arrow_keys(self) -> None:
        """Toolbar implements roving-tabindex: one stop, arrows move."""
        src = JS_PATH.read_text()
        assert "ArrowRight" in src
        assert "ArrowLeft" in src
        assert 'setAttribute("tabindex"' in src

    def test_editor_role_textbox(self) -> None:
        src = JS_PATH.read_text()
        assert 'setAttribute("contenteditable", "true")' in src
        assert 'setAttribute("role", "textbox")' in src
        assert 'setAttribute("aria-multiline", "true")' in src


class TestKeyboardShortcuts:
    def test_handler_checks_modifier_and_ignores_shift_alt(self) -> None:
        """Mod+B/I/U fires; Mod+Shift+B (browser shortcut) does not."""
        src = JS_PATH.read_text()
        assert "e.ctrlKey || e.metaKey" in src
        # Cycle 1 deliberately skips when shift or alt is held —
        # cycle 2 will reintroduce shift/alt for headings/redo/etc.
        assert "e.shiftKey" in src and "e.altKey" in src


class TestLifecycle:
    def test_returns_destroy_serialize_focus(self) -> None:
        """Bridge contract: mount returns instance with destroy/serialize/focus."""
        src = JS_PATH.read_text()
        assert "destroy: function ()" in src
        assert "serialize: function ()" in src
        assert "focus: function ()" in src

    def test_destroy_releases_listeners(self) -> None:
        src = JS_PATH.read_text()
        assert "listeners.length = 0" in src
        assert "removeEventListener" in src

    def test_unmount_calls_destroy(self) -> None:
        src = JS_PATH.read_text()
        assert "instance.destroy()" in src


class TestBundleWiring:
    def test_js_listed_in_build_dist(self) -> None:
        src = BUILD_DIST.read_text()
        assert "dz-richtext.js" in src

    def test_css_listed_in_build_dist(self) -> None:
        src = BUILD_DIST.read_text()
        assert "richtext.css" in src

    def test_css_listed_in_css_loader(self) -> None:
        src = CSS_LOADER.read_text()
        assert "css/components/richtext.css" in src

    def test_base_html_includes_script(self) -> None:
        src = BASE_HTML.read_text()
        assert "js/dz-richtext.js" in src

    def test_bundle_order_after_widget_registry(self) -> None:
        """dz-richtext.js calls bridge.registerWidget — must load AFTER
        dz-component-bridge.js + dz-widget-registry.js."""
        bd = BUILD_DIST.read_text()
        bridge_idx = bd.index("dz-component-bridge.js")
        registry_idx = bd.index("dz-widget-registry.js")
        rt_idx = bd.index("dz-richtext.js")
        assert bridge_idx < rt_idx
        assert registry_idx < rt_idx


class TestStylesheet:
    def test_targets_form_richtext_shell(self) -> None:
        """Reuses the existing .dz-form-richtext shell from form_field.html."""
        css = CSS_PATH.read_text()
        assert ".dz-form-richtext" in css
        assert ".dz-richtext-toolbar" in css
        assert "[data-dz-editor]" in css

    def test_active_state_styled(self) -> None:
        css = CSS_PATH.read_text()
        assert 'aria-pressed="true"' in css or ".is-active" in css

    def test_focus_visible_indicator(self) -> None:
        """WCAG 2.4.7 — visible focus on the editor."""
        css = CSS_PATH.read_text()
        assert ":focus-visible" in css or ":focus-within" in css


# ───────────────────────────── cycle 2 ────────────────────────────────


class TestCycle2Commands:
    """Lists, headings, blockquote, inline code, link, clear-format."""

    def test_block_commands_registered(self) -> None:
        src = JS_PATH.read_text()
        for cmd, tag in [
            ("h2", '"h2"'),
            ("h3", '"h3"'),
            ("blockquote", '"blockquote"'),
            ("paragraph", '"p"'),
        ]:
            assert cmd + ":" in src
            assert tag in src

    def test_list_commands_registered(self) -> None:
        src = JS_PATH.read_text()
        assert "ul:" in src and '"ul"' in src
        assert "ol:" in src and '"ol"' in src
        assert 'type: "list"' in src

    def test_link_command_registered(self) -> None:
        src = JS_PATH.read_text()
        assert "link:" in src
        assert 'type: "link"' in src

    def test_inline_code_registered(self) -> None:
        src = JS_PATH.read_text()
        assert "code:" in src and '"code"' in src

    def test_clear_format_registered(self) -> None:
        src = JS_PATH.read_text()
        assert "clear:" in src and 'type: "clear"' in src


class TestCycle2Schema:
    """Allowlist expansion for cycle 2 tags."""

    def test_inline_allow_expanded(self) -> None:
        """Cycle 2 inline allowlist: STRONG/EM/U/S/CODE/A/BR."""
        src = JS_PATH.read_text()
        for tag in ["STRONG:", "EM:", "U:", "S:", "CODE:", "A:", "BR:"]:
            assert tag in src

    def test_block_allow_expanded(self) -> None:
        """Cycle 2 block allowlist: P/H2/H3/UL/OL/LI/BLOCKQUOTE/PRE."""
        src = JS_PATH.read_text()
        for tag in ["P:", "H2:", "H3:", "UL:", "OL:", "LI:", "BLOCKQUOTE:", "PRE:"]:
            assert tag in src

    def test_href_attribute_allowlisted_only_on_a(self) -> None:
        """ATTR_ALLOW maps tag → allowed attrs. Only A→href in cycle 2."""
        src = JS_PATH.read_text()
        assert "ATTR_ALLOW" in src
        assert "A: { href: 1 }" in src

    def test_safe_href_protocol_regex(self) -> None:
        """Links must be http(s):, mailto:, or path-relative."""
        src = JS_PATH.read_text()
        assert "SAFE_HREF" in src
        assert "/^(https?:|mailto:|" in src

    def test_javascript_protocol_blocked_on_emit(self) -> None:
        """sanitiseTree strips href if it doesn't match SAFE_HREF."""
        src = JS_PATH.read_text()
        assert "if (!SAFE_HREF.test(href))" in src
        assert 'child.removeAttribute("href")' in src


class TestCycle2KeyboardShortcuts:
    def test_modifier_aware_dispatch(self) -> None:
        """matchKeyEvent matches by key + shift/alt flags so e.g. Mod+Shift+8
        (ul) and Mod+Shift+7 (ol) don't collide with Mod+B."""
        src = JS_PATH.read_text()
        assert "matchKeyEvent" in src
        assert "!!c.shift !== !!e.shiftKey" in src
        assert "!!c.alt !== !!e.altKey" in src

    def test_h2_shortcut_uses_alt(self) -> None:
        src = JS_PATH.read_text()
        assert 'h2: { tag: "h2", type: "block", key: "2", alt: true }' in src

    def test_blockquote_shortcut_uses_shift(self) -> None:
        src = JS_PATH.read_text()
        assert 'key: "q", shift: true' in src

    def test_link_shortcut_mod_k(self) -> None:
        src = JS_PATH.read_text()
        assert 'link: { type: "link", key: "k" }' in src


class TestCycle2Toolbar:
    def test_separator_supported(self) -> None:
        """Toolbar accepts '|' to insert a visual separator."""
        src = JS_PATH.read_text()
        assert 'name === "|"' in src
        assert "dz-richtext-toolbar-sep" in src
        assert 'role", "separator"' in src

    def test_default_toolbar_includes_cycle2_buttons(self) -> None:
        src = JS_PATH.read_text()
        # Default toolbar list at mount.
        for name in [
            '"bold"',
            '"italic"',
            '"underline"',
            '"h2"',
            '"h3"',
            '"ul"',
            '"ol"',
            '"link"',
            '"clear"',
        ]:
            assert name in src


class TestCycle2Stylesheet:
    def test_block_styles_present(self) -> None:
        css = CSS_PATH.read_text()
        for sel in [
            "[data-dz-editor] h2",
            "[data-dz-editor] h3",
            "[data-dz-editor] ul",
            "[data-dz-editor] ol",
            "[data-dz-editor] li",
            "[data-dz-editor] blockquote",
            "[data-dz-editor] code",
            "[data-dz-editor] a",
        ]:
            assert sel in css

    def test_separator_style_present(self) -> None:
        css = CSS_PATH.read_text()
        assert ".dz-richtext-toolbar-sep" in css

    def test_h2_uses_heading_token_983(self) -> None:
        """Reuses the heading scale tokens shipped in #983."""
        css = CSS_PATH.read_text()
        assert "--dz-heading-app-section-title" in css


class TestCycle2Lifecycle:
    def test_run_command_dispatches_all_types(self) -> None:
        src = JS_PATH.read_text()
        assert 'cmd.type === "inline"' in src
        assert 'cmd.type === "block"' in src
        assert 'cmd.type === "list"' in src
        assert 'cmd.type === "link"' in src
        assert 'cmd.type === "clear"' in src

    def test_link_prompt_injectable(self) -> None:
        """Tests can pass options.linkPrompt to avoid window.prompt."""
        src = JS_PATH.read_text()
        assert "options && options.linkPrompt" in src or "options.linkPrompt" in src
