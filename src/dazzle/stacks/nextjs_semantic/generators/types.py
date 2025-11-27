"""
TypeScript type definitions generator.

Generates TypeScript types from DAZZLE IR:
- Entity types
- Attention signal types
- Layout plan types
- Workspace types
"""

from pathlib import Path

from ....core import ir


class LayoutTypesGenerator:
    """Generate TypeScript type definitions from layout IR."""

    def __init__(self, spec: ir.AppSpec, project_path: Path, layout_plans: dict):
        self.spec = spec
        self.project_path = project_path
        self.layout_plans = layout_plans

    def generate(self) -> None:
        """Generate all TypeScript type files."""
        self._generate_layout_types()
        self._generate_entity_types()
        self._generate_signal_types()

    def _generate_layout_types(self) -> None:
        """Generate layout types (LayoutArchetype, LayoutPlan, etc.)."""
        content = '''/**
 * Layout Engine Types
 *
 * TypeScript types for semantic layout system.
 * Generated from DAZZLE IR.
 */

export enum LayoutArchetype {
  FOCUS_METRIC = "focus_metric",
  SCANNER_TABLE = "scanner_table",
  DUAL_PANE_FLOW = "dual_pane_flow",
  MONITOR_WALL = "monitor_wall",
  COMMAND_CENTER = "command_center",
}

export enum AttentionSignalKind {
  KPI = "kpi",
  TABLE = "table",
  CHART = "chart",
  ITEM_LIST = "item_list",
  DETAIL_VIEW = "detail_view",
  FORM = "form",
  SEARCH = "search",
  TASK_LIST = "task_list",
  ALERT_FEED = "alert_feed",
  MEDIA_GALLERY = "media_gallery",
}

export interface AttentionSignal {
  id: string;
  kind: AttentionSignalKind;
  label: string;
  source: string;
  attention_weight: number;
  urgency?: number;
  interaction_frequency?: number;
  density_preference?: string;
  mode?: string;
  constraints?: Record<string, unknown>;
}

export interface LayoutSurface {
  id: string;
  archetype: LayoutArchetype;
  capacity: number;
  priority: number;
  assigned_signals: string[];
}

export interface LayoutPlan {
  workspace_id: string;
  persona_id: string | null;
  archetype: LayoutArchetype;
  surfaces: LayoutSurface[];
  over_budget_signals: string[];
  warnings: string[];
  metadata: Record<string, unknown>;
}

export interface WorkspaceLayout {
  id: string;
  label: string;
  persona_targets?: string[];
  attention_budget: number;
  time_horizon?: string;
  engine_hint?: string;
  attention_signals: AttentionSignal[];
}
'''
        types_dir = self.project_path / "src" / "types"
        types_dir.mkdir(parents=True, exist_ok=True)
        output_path = types_dir / "layout.ts"
        output_path.write_text(content)

    def _generate_entity_types(self) -> None:
        """Generate TypeScript types from DAZZLE entities."""
        if not self.spec.domain or not self.spec.domain.entities:
            return

        type_defs = []

        for entity in self.spec.domain.entities:
            fields = []
            fields.append("  id: string;")

            if entity.fields:
                for field in entity.fields:
                    ts_type = self._map_field_type(field.type)
                    optional = "?" if not field.required else ""
                    fields.append(f"  {field.name}{optional}: {ts_type};")

            type_def = f'''export interface {entity.name} {{
{chr(10).join(fields)}
}}'''
            type_defs.append(type_def)

        content = f'''/**
 * Entity Types
 *
 * TypeScript types for domain entities.
 * Generated from DAZZLE DSL entities.
 */

{chr(10).join(type_defs)}
'''

        types_dir = self.project_path / "src" / "types"
        types_dir.mkdir(parents=True, exist_ok=True)
        output_path = types_dir / "entities.ts"
        output_path.write_text(content)

    def _generate_signal_types(self) -> None:
        """Generate TypeScript types for signals from workspaces."""
        if not self.spec.ux or not self.spec.ux.workspaces:
            return

        # Collect all unique signal kinds used
        signal_kinds = set()
        for workspace in self.spec.ux.workspaces:
            for signal in workspace.attention_signals:
                signal_kinds.add(signal.kind.value)

        content = f'''/**
 * Signal Data Types
 *
 * TypeScript types for attention signal data.
 * Generated from DAZZLE workspace signals.
 */

import {{ AttentionSignal, AttentionSignalKind }} from './layout';

// Signal kinds used in this app
export const USED_SIGNAL_KINDS = {list(signal_kinds)!r} as const;

export type SignalData = {{
  signal: AttentionSignal;
  data: unknown;
}};
'''

        types_dir = self.project_path / "src" / "types"
        types_dir.mkdir(parents=True, exist_ok=True)
        output_path = types_dir / "signals.ts"
        output_path.write_text(content)

    def _map_field_type(self, dazzle_type: str) -> str:
        """Map DAZZLE field type to TypeScript type."""
        type_mapping = {
            "str": "string",
            "int": "number",
            "float": "number",
            "bool": "boolean",
            "date": "string",  # ISO date string
            "datetime": "string",  # ISO datetime string
            "text": "string",
            "email": "string",
            "url": "string",
            "json": "Record<string, unknown>",
        }
        return type_mapping.get(dazzle_type, "unknown")


__all__ = ["LayoutTypesGenerator"]
