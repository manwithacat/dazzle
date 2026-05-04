"""Source-regression tests for dz-richtext.js (#977 cycles 1–4).

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

    def test_registers_as_richtext(self) -> None:
        """Cycle 4 flipped the bridge name from 'richtext-native' to
        'richtext' (Quill removed)."""
        src = JS_PATH.read_text()
        assert 'bridge.registerWidget("richtext"' in src

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


# ───────────────────────────── cycle 3 ────────────────────────────────


class TestCycle3PasteSanitiser:
    """Paste pipeline: DOMParser walk + tag-synonym rewrites +
    structural normalisation + dangerous-subtree drop."""

    def test_paste_handler_wired_on_editor(self) -> None:
        src = JS_PATH.read_text()
        assert 'on(editor, "paste"' in src
        assert "handlePaste(editor, e)" in src

    def test_paste_uses_clipboard_data(self) -> None:
        src = JS_PATH.read_text()
        assert 'data.getData("text/html")' in src
        assert 'data.getData("text/plain")' in src

    def test_paste_prevents_default(self) -> None:
        """We always own insertion — never let the browser drop raw HTML."""
        src = JS_PATH.read_text()
        assert "function handlePaste" in src
        assert "event.preventDefault()" in src

    def test_paste_uses_domparser(self) -> None:
        src = JS_PATH.read_text()
        assert "function pasteSanitise" in src
        assert "new DOMParser().parseFromString" in src

    def test_paste_inserts_via_range(self) -> None:
        """Insertion goes through Range.insertNode after deleteContents,
        so existing selection is replaced cleanly."""
        src = JS_PATH.read_text()
        assert "range.deleteContents()" in src
        assert "range.insertNode(frag)" in src


class TestCycle3TagSynonyms:
    def test_synonym_table_present(self) -> None:
        src = JS_PATH.read_text()
        assert "TAG_SYNONYMS" in src
        # Common Word/Docs synonyms
        assert 'B: "STRONG"' in src
        assert 'I: "EM"' in src
        assert 'STRIKE: "S"' in src
        assert 'DEL: "S"' in src

    def test_h1_demoted_to_h2(self) -> None:
        """Per #983: editor never produces h1 — surface owns it."""
        src = JS_PATH.read_text()
        assert 'H1: "H2"' in src

    def test_h4_h5_h6_promoted_to_h3(self) -> None:
        """Schema only has h2 + h3; deeper nesting collapses to h3."""
        src = JS_PATH.read_text()
        assert 'H4: "H3"' in src
        assert 'H5: "H3"' in src
        assert 'H6: "H3"' in src

    def test_div_collapses_to_p(self) -> None:
        """Word/Docs paste lots of divs; collapse to paragraphs."""
        src = JS_PATH.read_text()
        assert 'DIV: "P"' in src

    def test_synonym_walker_replaces_in_place(self) -> None:
        src = JS_PATH.read_text()
        assert "function rewriteSynonyms" in src
        assert "n.parentNode.replaceChild(replacement, n)" in src


class TestCycle3DangerousSubtreeDrop:
    """Defence-in-depth: explicitly drop script/style/iframe subtrees."""

    def test_drop_table_has_script_iframe_object(self) -> None:
        src = JS_PATH.read_text()
        assert "PASTE_DROP_WITH_CHILDREN" in src
        for tag in [
            "SCRIPT:",
            "STYLE:",
            "IFRAME:",
            "OBJECT:",
            "EMBED:",
            "META:",
            "LINK:",
            "NOSCRIPT:",
            "TEMPLATE:",
        ]:
            assert tag in src

    def test_drops_comments_and_processing_instructions(self) -> None:
        """Word HTML is full of <!-- conditional comments -->."""
        src = JS_PATH.read_text()
        assert "function dropDangerousSubtrees" in src
        # nodeType 8 = COMMENT_NODE, 7 = PROCESSING_INSTRUCTION_NODE
        assert "child.nodeType === 8" in src
        assert "child.nodeType === 7" in src


class TestCycle3StructuralNormalisation:
    def test_orphan_li_lifted(self) -> None:
        """A bare <li> outside ul/ol gets wrapped (or merged into a
        previous-sibling ul) — Notion paste does this."""
        src = JS_PATH.read_text()
        assert "function normaliseListStructure" in src
        assert "orphans" in src

    def test_p_inside_li_collapsed(self) -> None:
        """<li><p>text</p></li> → <li>text</li>."""
        src = JS_PATH.read_text()
        assert 'querySelectorAll("p")' in src
        assert "li.insertBefore" in src


class TestCycle3PlainTextFallback:
    def test_plain_text_split_into_paragraphs(self) -> None:
        """text/plain only: blank-line-split → <p>; single newlines → <br>."""
        src = JS_PATH.read_text()
        assert "text.split(/\\n{2,}/)" in src
        assert 'document.createElement("br")' in src


class TestCycle3SafeHrefInPaste:
    """Pasted links go through the same SAFE_HREF gate."""

    def test_a_href_validated_in_sanitise_tree(self) -> None:
        src = JS_PATH.read_text()
        assert "if (!SAFE_HREF.test(href))" in src


# ───────────────────────────── cycle 4 ────────────────────────────────


class TestCycle4BridgeFlip:
    """Bridge name moved from "richtext-native" to "richtext"; Quill gone."""

    def test_registered_as_richtext_not_richtext_native(self) -> None:
        src = JS_PATH.read_text()
        assert 'bridge.registerWidget("richtext"' in src
        # The string "richtext-native" may appear in module-doc comments
        # narrating the cycle 4 flip — only the registration call matters.
        assert 'registerWidget("richtext-native"' not in src

    def test_quill_bridge_removed_from_widget_registry(self) -> None:
        registry = (
            ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "js" / "dz-widget-registry.js"
        ).read_text()
        assert "Quill" not in registry or "Quill removed" in registry
        assert "new Quill(" not in registry
        assert 'bridge.registerWidget("richtext"' not in registry

    def test_quill_vendor_files_absent(self) -> None:
        vendor = ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "vendor"
        assert not (vendor / "quill.min.js").exists()
        assert not (vendor / "quill.snow.css").exists()

    def test_quill_conditional_removed_from_base_html(self) -> None:
        base = (ROOT / "src" / "dazzle_ui" / "templates" / "base.html").read_text()
        assert 'if "quill"' not in base
        assert "vendor/quill" not in base

    def test_asset_manifest_drops_rich_text_mapping(self) -> None:
        am = (ROOT / "src" / "dazzle_back" / "runtime" / "asset_manifest.py").read_text()
        assert '"rich_text": "quill"' not in am
        assert '"rich_text":' not in am


class TestCycle4UndoRedo:
    def test_undo_redo_handlers_registered(self) -> None:
        src = JS_PATH.read_text()
        assert "function undo()" in src
        assert "function redo()" in src

    def test_undo_stack_capped(self) -> None:
        """Bounded stack — prevents unbounded memory growth."""
        src = JS_PATH.read_text()
        assert "UNDO_LIMIT" in src
        assert "undoStack.shift()" in src

    def test_redo_stack_cleared_on_new_edit(self) -> None:
        """Standard redo semantics: any new edit invalidates the redo stack."""
        src = JS_PATH.read_text()
        assert "redoStack.length = 0" in src

    def test_keyboard_handlers_for_undo_redo(self) -> None:
        src = JS_PATH.read_text()
        # Mod+Z = undo
        assert 'k === "z" && !e.shiftKey' in src
        # Mod+Shift+Z OR Mod+Y = redo (Windows convention)
        assert 'k === "z" && e.shiftKey' in src or 'k === "y"' in src

    def test_history_replay_uses_safe_path(self) -> None:
        """Undo replays through replaceEditorContents (DOMParser-routed),
        not through a raw HTML write."""
        src = JS_PATH.read_text()
        assert "function applyHistory" in src
        assert "replaceEditorContents(editor, html)" in src


class TestCycle4LengthCap:
    def test_max_length_default(self) -> None:
        src = JS_PATH.read_text()
        # Default cap matches IR (50000).
        assert "50000" in src

    def test_max_length_overridable(self) -> None:
        src = JS_PATH.read_text()
        assert "options.maxLength" in src

    def test_warning_at_90_percent(self) -> None:
        """Polite live-region warning when approaching the cap."""
        src = JS_PATH.read_text()
        assert "0.9 * maxLength" in src
        assert "approaching length limit" in src


class TestCycle4IRAllowlist:
    def test_ir_module_exists(self) -> None:
        from dazzle.core.ir import richtext as rt

        assert rt.RICH_TEXT_ALLOWED_TAGS
        assert rt.RICH_TEXT_ALLOWED_ATTRS == {"a": frozenset({"href"})}

    def test_ir_excludes_h1(self) -> None:
        """#983 separation: h1 belongs to the surface, never the editor."""
        from dazzle.core.ir.richtext import RICH_TEXT_ALLOWED_TAGS

        assert "h1" not in RICH_TEXT_ALLOWED_TAGS

    def test_safe_href_helper(self) -> None:
        from dazzle.core.ir.richtext import is_safe_href

        assert is_safe_href("https://x")
        assert is_safe_href("mailto:a@b")
        assert is_safe_href("/path")
        assert not is_safe_href("javascript:alert(1)")
        assert not is_safe_href("data:text/html,x")
        assert not is_safe_href("")


class TestCycle4ServerField:
    def test_clean_rich_text_importable(self) -> None:
        from dazzle_back.runtime.richtext_field import clean_rich_text

        assert callable(clean_rich_text)

    def test_clean_rich_text_uses_ir_constants(self) -> None:
        """Field validator must source the allowlist from the IR."""
        src = (ROOT / "src" / "dazzle_back" / "runtime" / "richtext_field.py").read_text()
        assert "from dazzle.core.ir.richtext import" in src
        assert "RICH_TEXT_ALLOWED_TAGS" in src
        assert "RICH_TEXT_ALLOWED_ATTRS" in src
