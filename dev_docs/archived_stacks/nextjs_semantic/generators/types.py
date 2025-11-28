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

/**
 * Engine Variants
 *
 * Variants control visual density and spacing for the same archetype.
 * - classic: Default balanced layout (1.0x spacing)
 * - dense: Higher information density for power users (0.75x spacing)
 * - comfortable: More whitespace for readability (1.25x spacing)
 */
export enum EngineVariant {
  CLASSIC = "classic",
  DENSE = "dense",
  COMFORTABLE = "comfortable",
}

export interface VariantConfig {
  name: string;
  description: string;
  spacingScale: number;
  fontScale: number;
  itemsPerRowModifier: number;
  borderRadiusScale: number;
  minElementHeight: string;
  tailwindClasses: {
    container: string;
    card: string;
    grid: string;
    textSm: string;
    textBase: string;
    textLg: string;
    heading: string;
  };
}

export const VARIANT_CONFIGS: Record<EngineVariant, VariantConfig> = {
  [EngineVariant.CLASSIC]: {
    name: "classic",
    description: "Balanced layout with standard spacing",
    spacingScale: 1.0,
    fontScale: 1.0,
    itemsPerRowModifier: 0,
    borderRadiusScale: 1.0,
    minElementHeight: "auto",
    tailwindClasses: {
      container: "p-4 sm:p-6",
      card: "p-4 sm:p-6 rounded-lg",
      grid: "gap-4 sm:gap-6",
      textSm: "text-sm",
      textBase: "text-base",
      textLg: "text-lg",
      heading: "text-2xl font-bold",
    },
  },
  [EngineVariant.DENSE]: {
    name: "dense",
    description: "Higher density for power users and experts",
    spacingScale: 0.75,
    fontScale: 0.9,
    itemsPerRowModifier: 1,
    borderRadiusScale: 0.75,
    minElementHeight: "2rem",
    tailwindClasses: {
      container: "p-2 sm:p-3",
      card: "p-2 sm:p-3 rounded",
      grid: "gap-2 sm:gap-3",
      textSm: "text-xs",
      textBase: "text-sm",
      textLg: "text-base",
      heading: "text-xl font-semibold",
    },
  },
  [EngineVariant.COMFORTABLE]: {
    name: "comfortable",
    description: "More whitespace for readability and casual use",
    spacingScale: 1.25,
    fontScale: 1.1,
    itemsPerRowModifier: -1,
    borderRadiusScale: 1.25,
    minElementHeight: "4rem",
    tailwindClasses: {
      container: "p-6 sm:p-8",
      card: "p-6 sm:p-8 rounded-xl",
      grid: "gap-6 sm:gap-8",
      textSm: "text-base",
      textBase: "text-lg",
      textLg: "text-xl",
      heading: "text-3xl font-bold",
    },
  },
};

/**
 * Get the recommended variant based on persona characteristics.
 */
export function getVariantForPersona(
  proficiencyLevel?: string,
  sessionStyle?: string
): EngineVariant {
  // Experts doing deep work prefer dense layouts
  if (proficiencyLevel === "expert" && sessionStyle === "deep_work") {
    return EngineVariant.DENSE;
  }
  // Novices or glancers prefer comfortable layouts
  if (proficiencyLevel === "novice" || sessionStyle === "glance") {
    return EngineVariant.COMFORTABLE;
  }
  // Default to classic
  return EngineVariant.CLASSIC;
}

/**
 * Calculate grid columns adjusted for variant.
 */
export function getGridColumns(
  baseColumns: number,
  variant: EngineVariant,
  breakpoint: "default" | "sm" | "md" | "lg" | "xl" = "default"
): number {
  const config = VARIANT_CONFIGS[variant];
  const adjusted = baseColumns + config.itemsPerRowModifier;

  const maxColumns: Record<string, number> = {
    default: 2,
    sm: 3,
    md: 4,
    lg: 6,
    xl: 8,
  };

  return Math.max(1, Math.min(adjusted, maxColumns[breakpoint] || 4));
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
                    ts_type = self._map_field_type(field.type.kind)
                    optional = "?" if not field.is_required else ""
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

    def _map_field_type(self, field_type_kind) -> str:
        """Map DAZZLE field type to TypeScript type."""
        from dazzle.core.ir import FieldTypeKind

        type_mapping = {
            FieldTypeKind.STR: "string",
            FieldTypeKind.TEXT: "string",
            FieldTypeKind.INT: "number",
            FieldTypeKind.DECIMAL: "number",
            FieldTypeKind.BOOL: "boolean",
            FieldTypeKind.DATE: "string",  # ISO date string
            FieldTypeKind.DATETIME: "string",  # ISO datetime string
            FieldTypeKind.UUID: "string",
            FieldTypeKind.ENUM: "string",  # TODO: Could generate union type
            FieldTypeKind.REF: "string",  # TODO: Could reference entity type
            FieldTypeKind.EMAIL: "string",
        }
        return type_mapping.get(field_type_kind, "unknown")


__all__ = ["LayoutTypesGenerator"]
