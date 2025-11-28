"""
Dazzle Native Runtime - UI (DNR-UI)

LLM-first UI specification and runtime for Dazzle applications.

This package provides:
- UISpec: Complete UI specification types (workspaces, components, themes)
- Runtime: Native UI runtime (signals-based state + DOM rendering)
- Components: Built-in primitive and pattern components
- Converters: Transform Dazzle AppSpec to UISpec
"""

__version__ = "0.3.0"

from dazzle_dnr_ui.specs.ui_spec import UISpec

__all__ = ["UISpec"]
