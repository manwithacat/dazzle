"""Phase 4B.5.b.2.i (v0.66.121): byte-equivalence + structural tests
for the typed `WorkspaceToolbar` primitive.

The toolbar is a fixed-shape singleton: Reset button + Save button
with five `data-dz-when` saveState spans (clean / dirty / saving /
saved / error). The Alpine state machine that drives it (saveState,
resetLayout, save, _saveError) is owned by the parent
dashboard-builder controller on the WorkspaceShell wrapper (F4e).
"""

from __future__ import annotations

from dazzle.render.fragment import FragmentRenderer, WorkspaceToolbar

# The legacy `_content.html` toolbar block, extracted verbatim. Pinned
# here as a literal so any drift between the typed primitive and the
# legacy template is caught immediately. When updating either side
# (renderer constant or legacy template), update this fixture too.
_LEGACY_TOOLBAR_HTML = """<div class="dz-workspace-toolbar">
    <div class="dz-workspace-toolbar-spacer"></div>
    <button @click="resetLayout()" class="dz-workspace-reset">
      Reset
    </button>
    <button @click="save()"
            :disabled="saveState === 'clean' || saveState === 'saving' || saveState === 'saved'"
            :data-dz-save-state="saveState"
            :title="saveState === 'error' ? _saveError : ''"
            class="dz-workspace-save">
      <span x-cloak x-show="saveState === 'clean'">Saved</span>
      <span x-cloak x-show="saveState === 'dirty'">Save layout</span>
      <span x-cloak x-show="saveState === 'saving'" class="dz-workspace-save-busy">
        <svg class="dz-workspace-save-busy-icon" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
        Saving
      </span>
      <span x-cloak x-show="saveState === 'saved'" class="dz-workspace-save-busy">
        <svg class="dz-workspace-save-busy-icon" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>
        Saved
      </span>
      <span x-cloak x-show="saveState === 'error'">Retry</span>
    </button>
  </div>"""


def _render() -> str:
    return FragmentRenderer().render(WorkspaceToolbar())


# The byte-parity-with-legacy test was RETIRED in Tier F4e: the toolbar
# contract deliberately changed from Alpine bindings to state-in-DOM
# (data-dz-action triggers + data-dz-when spans keyed off the save
# button's data-dz-save-state). The structural pins below hold the new
# contract; tests/unit/test_dashboard_builder_f4e.py pins it end-to-end.


def test_workspace_toolbar_carries_outer_class() -> None:
    """`<div class="dz-workspace-toolbar">` is the contract attribute
    the dashboard CSS keys off."""
    assert '<div class="dz-workspace-toolbar">' in _render()


def test_workspace_toolbar_emits_reset_button_with_action_trigger() -> None:
    """Reset button carries data-dz-action for the dashboard-builder's
    root click delegation (F4e; was an Alpine @click)."""
    html = _render()
    assert 'data-dz-action="reset"' in html
    assert 'class="dz-workspace-reset"' in html
    assert ">Reset<" in html


def test_workspace_toolbar_save_button_ssrs_state() -> None:
    """Save button SSRs the clean state, disabled; the controller's
    saveState setter drives data-dz-save-state/disabled/title from
    there (F4e state-in-DOM)."""
    html = _render()
    assert 'data-dz-action="save"' in html
    assert 'data-dz-save-state="clean"' in html
    assert "disabled" in html


def test_workspace_toolbar_emits_five_state_spans() -> None:
    """One span per saveState value, keyed by data-dz-when — CSS shows
    exactly the span matching the button's data-dz-save-state, so a
    degraded (no-JS) page shows only the SSR'd clean label (#866's
    stacked-labels failure can't occur)."""
    html = _render()
    for state in ("clean", "dirty", "saving", "saved", "error"):
        assert f'data-dz-when="{state}"' in html, f"missing state span for {state!r}"


def test_workspace_toolbar_busy_states_carry_their_own_svg_icons() -> None:
    """The `saving` and `saved` states are the two busy states that
    carry a leading SVG icon (spinner + checkmark respectively).
    The CSS class `dz-workspace-save-busy-icon` is the contract the
    spinner animation keys off."""
    html = _render()
    assert html.count('class="dz-workspace-save-busy-icon"') == 2
    # Spinner viewBox (24×24 with circle + arc path)
    assert 'viewBox="0 0 24 24"' in html
    # Checkmark viewBox (20×20 with check path)
    assert 'viewBox="0 0 20 20"' in html
    assert 'd="M16.707 5.293' in html


def test_workspace_toolbar_save_label_copy_matches_legacy() -> None:
    """The user-visible labels are hardcoded in the legacy template;
    the typed primitive matches verbatim. Saved (clean), Save layout
    (dirty), Saving / Saved (busy), Retry (error)."""
    html = _render()
    # 'Saved' appears twice (clean state + post-save success busy state)
    assert html.count(">Saved<") == 2
    assert ">Save layout<" in html
    assert ">Saving<" in html
    assert ">Retry<" in html
