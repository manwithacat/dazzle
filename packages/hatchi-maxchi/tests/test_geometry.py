"""Geometry gates — correctness properties of the rendered layout that a
pixel-diff baseline can't assert (a baseline only catches *changes*, so it
would happily bake a bug in — as nearly happened with the filter-select crop).

Regression pin (2026-07-04): the data-table filter `<select>` clipped the
bottom of its text. Cause: a fixed `height: 2rem` on a `border-box` control
left only ~14px of content once the UA's default ~8px vertical select padding
+ 1px borders were subtracted — shorter than the ~15px text.

Detection note: for a `<select>`/`<input>` the browser clips the text line
*inside* the box, so `scrollHeight == clientHeight` (the control doesn't
scroll) — an overflow check does NOT catch it. The reliable signal is that the
content box (clientHeight minus vertical padding) is smaller than the font-size
itself: a line of text cannot fit, so its top/bottom are cut off.
"""

# A line of text needs at least its font-size of vertical room (really ~1.2x
# for line-height:normal, but we only flag a *clear* deficit to avoid
# false-positives on deliberately tight designs). 0.5px absorbs rounding.
_CLIP_EPSILON = 0.5


def test_no_form_control_clips_its_text_vertically(page) -> None:  # type: ignore[no-untyped-def]
    clipped = page.evaluate(
        """(eps) => {
          const out = [];
          // Text-bearing form controls with a fixed-ish box that can crop.
          // Checkbox/radio/hidden inputs have no text line, so skip them.
          const sel = 'select, textarea, input:not([type=checkbox])'
                    + ':not([type=radio]):not([type=hidden])';
          for (const el of document.querySelectorAll(sel)) {
            if (el.offsetParent === null) continue;  // not rendered
            const cs = getComputedStyle(el);
            const font = parseFloat(cs.fontSize);
            // clientHeight = content + padding (excludes border). Subtract the
            // vertical padding to get the box the text line actually gets.
            const content = el.clientHeight
                          - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
            if (content + eps < font) {
              out.push({
                tag: el.tagName.toLowerCase(),
                cls: el.className || null,
                contentHeight: Math.round(content * 10) / 10,
                fontSize: font,
                text: (el.value || el.textContent || '').trim().slice(0, 30),
              });
            }
          }
          return out;
        }""",
        _CLIP_EPSILON,
    )
    assert not clipped, (
        "form controls whose content box is shorter than their font-size — the "
        "text line can't fit, so it's clipped (a fixed height too small once "
        "padding + borders are subtracted):\n" + "\n".join(str(c) for c in clipped)
    )


def test_no_visible_element_collapses_to_zero_paint(page) -> None:  # type: ignore[no-untyped-def]
    """Every VISIBLE element in a demo must paint a nonzero box. A pixel
    baseline can't catch this class of bug (it bakes the collapse in as the
    expected image): the 2026-07-06 case was the separator <hr>, whose UA
    `margin-inline: auto` absorbed all free space inside the flex-column
    demo stack — 1px tall, ZERO wide, rendered as a blank line.

    Exemptions are structural: unrendered subtrees (closed details/dialog,
    [hidden], display:none/visibility:hidden), table plumbing (col/colgroup),
    and the SR-only clip pattern (1px boxes pass the nonzero check anyway).
    """
    collapsed = page.evaluate(
        """() => {
          const out = [];
          for (const host of document.querySelectorAll('.hm-preview')) {
            for (const el of host.querySelectorAll('*')) {
              const tag = el.tagName.toLowerCase();
              if (['col', 'colgroup', 'option', 'optgroup', 'template',
                   'script', 'style', 'use', 'defs', 'symbol'].includes(tag)) continue;
              if (el.closest('[hidden]')) continue;
              if (el.closest('details:not([open])') && !el.matches('summary') &&
                  !el.closest('summary')) continue;
              if (el.closest('dialog:not([open])')) continue;
              // checkVisibility covers display:none ANCESTORS too — a child
              // of a hidden subtree keeps its own computed display value.
              if (el.checkVisibility && !el.checkVisibility()) continue;
              const s = getComputedStyle(el);
              if (s.display === 'none' || s.visibility === 'hidden') continue;
              const r = el.getBoundingClientRect();
              if (r.width === 0 || r.height === 0) {
                // an empty inline text holder with no styling is not a bug
                const painted = s.borderTopWidth !== '0px' || s.borderLeftWidth !== '0px'
                  || s.backgroundColor !== 'rgba(0, 0, 0, 0)' || el.children.length > 0
                  || (el.textContent || '').trim() !== '';
                if (!painted) continue;
                const comp = el.closest('.hm-comp');
                out.push((comp ? comp.id + ': ' : '') + tag + '.' + (el.className || '')
                  + ' -> ' + r.width + 'x' + r.height);
              }
            }
          }
          return out;
        }"""
    )
    assert not collapsed, (
        "visible elements painting a zero-size box (the collapsed-<hr> bug class):\n  "
        + "\n  ".join(collapsed)
    )
