"""
Next.js pages and routing generator.

Generates:
- App router pages for each workspace
- Root layout
- Home page
- Signal renderer component (placeholder)
"""

from pathlib import Path

from ....core import ir


class PagesGenerator:
    """Generate Next.js pages and routes."""

    def __init__(self, spec: ir.AppSpec, project_path: Path, layout_plans: dict):
        self.spec = spec
        self.project_path = project_path
        self.layout_plans = layout_plans

    def generate(self) -> None:
        """Generate all pages and components."""
        self._generate_root_layout()
        self._generate_home_page()
        self._generate_signal_renderer()
        self._generate_workspace_pages()

    def _generate_root_layout(self) -> None:
        """Generate root layout.tsx."""
        content = '''import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "''' + self.spec.title + '''",
  description: "Generated with DAZZLE",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
'''
        app_dir = self.project_path / "src" / "app"
        app_dir.mkdir(parents=True, exist_ok=True)
        output_path = app_dir / "layout.tsx"
        output_path.write_text(content)

    def _generate_home_page(self) -> None:
        """Generate home page.tsx."""
        # List all workspaces
        workspace_links = []
        if self.spec.ux and self.spec.ux.workspaces:
            for workspace in self.spec.ux.workspaces:
                workspace_links.append(
                    f'          <li key="{workspace.id}">\n'
                    f'            <a href="/{workspace.id}" '
                    f'className="text-blue-600 hover:text-blue-800 underline">\n'
                    f'              {workspace.label}\n'
                    f'            </a>\n'
                    f'          </li>'
                )

        links_html = '\n'.join(workspace_links) if workspace_links else \
                     '          <li className="text-gray-500">No workspaces defined</li>'

        content = f'''export default function Home() {{
  return (
    <main className="min-h-screen p-8 bg-gradient-to-br from-blue-50 to-indigo-50">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold mb-4 text-gray-900">{self.spec.title}</h1>
        <p className="text-lg text-gray-600 mb-8">
          Generated with DAZZLE Semantic Layout Engine
        </p>

        <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
          <h2 className="text-2xl font-semibold mb-4 text-gray-800">Workspaces</h2>
          <ul className="space-y-2">
{links_html}
          </ul>
        </div>

        <div className="mt-8 text-sm text-gray-500">
          <p>This application uses semantic layout archetypes:</p>
          <ul className="mt-2 list-disc list-inside space-y-1">
            <li>FOCUS_METRIC - Hero metric displays</li>
            <li>SCANNER_TABLE - Dense table views</li>
            <li>DUAL_PANE_FLOW - List + detail layouts</li>
            <li>MONITOR_WALL - Metric grids</li>
            <li>COMMAND_CENTER - Expert dashboards</li>
          </ul>
        </div>
      </div>
    </main>
  );
}}
'''
        app_dir = self.project_path / "src" / "app"
        output_path = app_dir / "page.tsx"
        output_path.write_text(content)

    def _generate_signal_renderer(self) -> None:
        """Generate SignalRenderer component (placeholder implementation)."""
        content = '''/**
 * Signal Renderer
 *
 * Renders attention signals based on their kind.
 * This is a placeholder implementation - customize for your data.
 */

import { AttentionSignal, AttentionSignalKind } from '@/types/layout';

interface SignalRendererProps {
  signal: AttentionSignal;
  data: unknown;
  variant?: 'hero' | 'context' | 'toolbar' | 'table' | 'list' | 'detail' | 'card' | 'compact' | 'toolbelt' | 'sidebar' | 'panel' | 'status';
}

export function SignalRenderer({ signal, data, variant = 'card' }: SignalRendererProps) {
  const variantClasses = {
    hero: 'text-6xl font-bold text-center',
    context: 'text-lg',
    toolbar: 'text-sm',
    table: '',
    list: 'hover:bg-gray-50 cursor-pointer p-3',
    detail: 'text-base',
    card: 'text-base',
    compact: 'text-sm',
    toolbelt: 'text-sm text-gray-300',
    sidebar: 'text-sm text-gray-300',
    panel: 'text-base text-gray-100',
    status: 'text-gray-400',
  };

  const className = variantClasses[variant] || '';

  // Render based on signal kind
  switch (signal.kind) {
    case AttentionSignalKind.KPI:
      return (
        <div className={className}>
          <div className="font-semibold text-gray-600 text-sm mb-1">{signal.label}</div>
          <div className="text-3xl font-bold text-blue-600">
            {data !== null && data !== undefined ? String(data) : '--'}
          </div>
        </div>
      );

    case AttentionSignalKind.TABLE:
      return (
        <div className={className}>
          <h3 className="font-semibold mb-4">{signal.label}</h3>
          <div className="border border-gray-200 rounded overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left text-sm font-semibold">Column 1</th>
                  <th className="px-4 py-2 text-left text-sm font-semibold">Column 2</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-t">
                  <td className="px-4 py-2 text-sm">Sample</td>
                  <td className="px-4 py-2 text-sm">Data</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      );

    case AttentionSignalKind.CHART:
      return (
        <div className={className}>
          <h3 className="font-semibold mb-4">{signal.label}</h3>
          <div className="h-48 bg-gray-100 rounded flex items-center justify-center">
            <span className="text-gray-400">Chart placeholder</span>
          </div>
        </div>
      );

    case AttentionSignalKind.ITEM_LIST:
    case AttentionSignalKind.TASK_LIST:
      return (
        <div className={className}>
          <h3 className="font-semibold mb-3">{signal.label}</h3>
          <ul className="space-y-2">
            <li className="flex items-center gap-2">
              <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
              <span>Item 1</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
              <span>Item 2</span>
            </li>
          </ul>
        </div>
      );

    case AttentionSignalKind.FORM:
      return (
        <div className={className}>
          <h3 className="font-semibold mb-4">{signal.label}</h3>
          <form className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Field</label>
              <input
                type="text"
                className="w-full px-3 py-2 border border-gray-300 rounded"
                placeholder="Enter value"
              />
            </div>
            <button className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
              Submit
            </button>
          </form>
        </div>
      );

    case AttentionSignalKind.SEARCH:
      return (
        <div className={className}>
          <input
            type="search"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg"
            placeholder={`Search ${signal.label}...`}
          />
        </div>
      );

    case AttentionSignalKind.ALERT_FEED:
      return (
        <div className={className}>
          <h3 className="font-semibold mb-3">{signal.label}</h3>
          <div className="space-y-2">
            <div className="p-3 bg-yellow-50 border border-yellow-200 rounded">
              <div className="font-medium text-yellow-800">Warning</div>
              <div className="text-sm text-yellow-700">Sample alert message</div>
            </div>
          </div>
        </div>
      );

    case AttentionSignalKind.DETAIL_VIEW:
      return (
        <div className={className}>
          <h3 className="font-semibold mb-4 text-2xl">{signal.label}</h3>
          <div className="space-y-3">
            <div>
              <div className="text-sm text-gray-600">Detail Field 1</div>
              <div className="font-medium">Value 1</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Detail Field 2</div>
              <div className="font-medium">Value 2</div>
            </div>
          </div>
        </div>
      );

    default:
      return (
        <div className={className}>
          <h3 className="font-semibold">{signal.label}</h3>
          <p className="text-sm text-gray-500 mt-1">
            Signal kind: {signal.kind}
          </p>
        </div>
      );
  }
}
'''
        signals_dir = self.project_path / "src" / "components" / "signals"
        signals_dir.mkdir(parents=True, exist_ok=True)
        output_path = signals_dir / "SignalRenderer.tsx"
        output_path.write_text(content)

    def _generate_workspace_pages(self) -> None:
        """Generate a page for each workspace."""
        if not self.spec.ux or not self.spec.ux.workspaces:
            return

        for workspace in self.spec.ux.workspaces:
            self._generate_workspace_page(workspace)

    def _generate_workspace_page(self, workspace: ir.WorkspaceLayout) -> None:
        """Generate a single workspace page."""
        plan = self.layout_plans.get(workspace.id)
        if not plan:
            return

        # Build signal map
        signal_defs = []
        for signal in workspace.attention_signals:
            signal_defs.append(
                f'    "{signal.id}": {{\n'
                f'      id: "{signal.id}",\n'
                f'      kind: AttentionSignalKind.{signal.kind.name},\n'
                f'      label: "{signal.label}",\n'
                f'      source: "{signal.source}",\n'
                f'      attention_weight: {signal.attention_weight},\n'
                f'    }}'
            )

        signals_map = ',\n'.join(signal_defs)

        content = f'''/**
 * Workspace: {workspace.label}
 *
 * Generated workspace page with semantic layout.
 * Archetype: {plan.archetype.value}
 */

import {{ ArchetypeRouter }} from '@/components/archetypes/ArchetypeRouter';
import {{ LayoutArchetype, AttentionSignalKind }} from '@/types/layout';

export default function {workspace.id.replace('_', '').capitalize()}Page() {{
  // Layout plan (generated from DSL)
  const layoutPlan = {{
    workspace_id: "{workspace.id}",
    persona_id: null,
    archetype: LayoutArchetype.{plan.archetype.name},
    surfaces: {str([
        {
            'id': s.id,
            'archetype': s.archetype.value,
            'capacity': s.capacity,
            'priority': s.priority,
            'assigned_signals': s.assigned_signals
        } for s in plan.surfaces
    ])},
    over_budget_signals: {plan.over_budget_signals},
    warnings: {plan.warnings},
    metadata: {{}},
  }};

  // Signal definitions
  const signals = {{
{signals_map}
  }};

  // Mock signal data (replace with real data fetching)
  const signalData = {{
    // Add your signal data here
  }};

  return (
    <ArchetypeRouter
      plan={{layoutPlan as any}}
      signals={{signals as any}}
      signalData={{signalData}}
    />
  );
}}
'''

        # Create workspace directory
        workspace_dir = self.project_path / "src" / "app" / workspace.id
        workspace_dir.mkdir(parents=True, exist_ok=True)
        output_path = workspace_dir / "page.tsx"
        output_path.write_text(content)


__all__ = ["PagesGenerator"]
