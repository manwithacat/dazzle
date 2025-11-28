# DAZZLE v0.3.0 Phase 5 - Advanced Archetypes & Variants

**Status**: Planning → In Progress
**Start Date**: 2025-11-28
**Focus**: Additional archetypes and engine variants
**Dependencies**: Phase 4 complete (all 5 archetypes, performance optimizations)

> **Context**: Phase 5 implements features from the "Future Enhancements (v0.4.0+)" section of the original v0.3.0 roadmap. These are optional but valuable additions to the UI Semantic Layout Engine.

---

## Phase 5 Overview

### Goals

1. Add 5th archetype: **COMMAND_CENTER** (operations dashboard)
2. Add engine variant: **Dense** (higher information density)
3. Improve archetype selection algorithm
4. Add archetype customization options
5. Prepare for v0.3.0 release

### Why These Features

**COMMAND_CENTER** fills a gap:
- Operations/monitoring dashboards need real-time alert focus
- Multiple signal streams with different urgencies
- Quick action buttons and status indicators
- Not well-served by existing archetypes

**Dense Engine Variant**:
- Power users want more information density
- Expert personas benefit from compact layouts
- Mobile users need efficient screen usage
- Simple implementation with high impact

---

## Week 13: COMMAND_CENTER Archetype

**Goal**: Implement 6th archetype for operations dashboards

### Tasks

- [ ] Design COMMAND_CENTER archetype specification
  - Primary: Alert feed with actions
  - Secondary: Status grid (system health)
  - Tertiary: Quick actions toolbar
  - Layout: Full-width, compact panels

- [ ] Implement archetype definition
  - Add to `LayoutArchetype` enum
  - Define surface capacities
  - Define signal kind mappings

- [ ] Update archetype selection algorithm
  - Select COMMAND_CENTER when:
    - Multiple alert signals present
    - Expert persona + high urgency signals
    - `engine_hint: "command_center"` specified

- [ ] Implement React component
  - Create `CommandCenter.tsx` archetype component
  - Alert feed with severity colors
  - Status grid with health indicators
  - Quick actions toolbar
  - Real-time update support

- [ ] Add loading and error states
  - Skeleton for alert feed
  - Error boundary for failed signals
  - Retry mechanism for updates

- [ ] Create example project
  - `examples/ops_dashboard/`
  - Multiple systems monitoring
  - Alert conditions
  - Quick response actions

### Deliverables

- `src/dazzle/ui/layout_engine/archetypes.py` (updated)
- `src/dazzle/stacks/nextjs_semantic/generators/archetypes.py` (updated)
- `examples/ops_dashboard/` (new)
- Tests for COMMAND_CENTER selection and rendering

**Estimate**: 3-4 days

---

## Week 14: Dense Engine Variant

**Goal**: Higher information density for power users

### Tasks

- [ ] Define Dense variant specification
  - Reduced padding/margins
  - Smaller typography scale
  - More items per row
  - Compact signal rendering

- [ ] Implement engine variant system
  - Add `engine_variant` to layout planning
  - Create variant configurations
  - Apply variant to surface rendering

- [ ] Create Dense variant configuration
  ```python
  class EngineVariant(str, Enum):
      CLASSIC = "classic"    # Default, balanced
      DENSE = "dense"        # Higher density
      COMFORTABLE = "comfortable"  # More whitespace

  DENSE_CONFIG = {
      "spacing_scale": 0.75,  # 75% of normal
      "font_scale": 0.9,      # 90% of normal
      "items_per_row": "+2",  # 2 more than normal
      "surface_padding": "compact",
  }
  ```

- [ ] Update archetype components
  - Accept variant prop
  - Apply variant styles
  - Responsive variant handling

- [ ] Add Tailwind variant classes
  - `.dense-*` utility classes
  - Configurable spacing
  - Font size adjustments

- [ ] Add persona-based variant selection
  - Expert persona → dense by default
  - Session style affects density
  - User preference override

### Deliverables

- `src/dazzle/ui/layout_engine/variants.py` (new)
- Updated archetype components with variant support
- Tailwind configuration updates
- Tests for variant rendering

**Estimate**: 3-4 days

---

## Week 15: Archetype Selection Improvements

**Goal**: Smarter, more predictable archetype selection

### Tasks

- [ ] Document current selection algorithm
  - Create flowchart/decision tree
  - Document edge cases
  - List all heuristics

- [ ] Add configurable selection thresholds
  ```python
  SELECTION_CONFIG = {
      "focus_metric": {
          "min_kpi_weight": 0.7,
          "max_signals": 3,
      },
      "scanner_table": {
          "min_table_weight": 0.6,
          "requires_table_signal": True,
      },
      # ...
  }
  ```

- [ ] Implement selection scoring system
  - Score each archetype for given signals
  - Return ranked list of matches
  - Select highest score
  - Provide confidence level

- [ ] Add selection debugging
  - `dazzle layout-plan --explain` flag
  - Show why archetype was selected
  - Show alternative scores

- [ ] Update archetype selection guide
  - Document new algorithm
  - Add decision tree diagram
  - Include troubleshooting tips

### Deliverables

- Improved selection algorithm
- Selection debugging command
- Updated documentation
- Higher selection accuracy

**Estimate**: 2-3 days

---

## Week 16: Archetype Customization

**Goal**: Allow fine-tuning of archetype behavior

### Tasks

- [ ] Add archetype customization options
  ```dsl
  workspace dashboard "Dashboard":
    engine_hint: "focus_metric"
    engine_options:
      hero_height: "tall"      # tall, medium, compact
      context_columns: 3        # Number of context cards
      show_empty_slots: false   # Hide unused surfaces
  ```

- [ ] Implement customization in IR
  - Add `engine_options` to WorkspaceLayout
  - Validate options per archetype
  - Pass to layout planning

- [ ] Apply customizations in components
  - Read options from layout plan
  - Apply to component rendering
  - Fallback to defaults

- [ ] Document customization options
  - Options per archetype
  - Examples and use cases
  - Best practices

### Deliverables

- DSL support for `engine_options`
- IR types for customization
- Component support for options
- Documentation

**Estimate**: 2-3 days

---

## Week 17: Release Preparation

**Goal**: Prepare v0.3.0 for release

### Tasks

- [ ] Create release notes
  - All features since v0.2.x
  - Migration guide
  - Breaking changes (if any)
  - Known limitations

- [ ] Update version numbers
  - `pyproject.toml`
  - `__version__`
  - Documentation references

- [ ] Final testing
  - Run all tests
  - Test all examples
  - Cross-platform testing
  - Performance verification

- [ ] Update main ROADMAP.md
  - Mark v0.3.0 features complete
  - Update timeline
  - Plan v0.4.0

- [ ] Create release
  - Tag release
  - Build distribution
  - Update Homebrew formula
  - Announce release

### Deliverables

- Release notes
- v0.3.0 release tag
- Updated Homebrew formula
- Announcement post

**Estimate**: 2-3 days

---

## Phase 5 Summary

| Week | Focus | Duration |
|------|-------|----------|
| 13 | COMMAND_CENTER archetype | 3-4 days |
| 14 | Dense engine variant | 3-4 days |
| 15 | Selection improvements | 2-3 days |
| 16 | Archetype customization | 2-3 days |
| 17 | Release preparation | 2-3 days |

**Total**: 12-17 days (~3-4 weeks)

---

## Success Criteria

Phase 5 is complete when:

- [ ] COMMAND_CENTER archetype works end-to-end
- [ ] Dense variant reduces visual density by ~25%
- [ ] Archetype selection has debugging output
- [ ] Customization options work in DSL
- [ ] v0.3.0 release is published
- [ ] All tests pass
- [ ] Documentation is complete

---

## Deferred to v0.4.0

The following features remain for future versions:

1. **Additional Archetypes**
   - Kanban Board
   - Analytics Dashboard
   - Settings Panel

2. **Additional Engine Variants**
   - Playful (card-heavy, colorful)
   - Minimal (clean, spacious)
   - Accessibility (high-contrast, keyboard-first)

3. **Advanced Features**
   - Layout Animations
   - Adaptive Layouts (time-of-day)
   - Layout Composition
   - Custom Archetypes
   - Visual Editor

---

**Status**: Ready to Begin
**Next Action**: Start Week 13 (COMMAND_CENTER archetype)
