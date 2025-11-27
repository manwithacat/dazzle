"""
Archetype component generators.

Generates React components for all 5 layout archetypes:
- FOCUS_METRIC: Hero metric + context
- SCANNER_TABLE: Dense table view
- DUAL_PANE_FLOW: List + detail
- MONITOR_WALL: Grid of metrics
- COMMAND_CENTER: Expert dashboard
"""

from pathlib import Path

from ....core import ir


class ArchetypeComponentsGenerator:
    """Generate React components for layout archetypes."""

    def __init__(self, spec: ir.AppSpec, project_path: Path):
        self.spec = spec
        self.project_path = project_path

    def generate(self) -> None:
        """Generate all archetype components."""
        self._generate_focus_metric()
        self._generate_scanner_table()
        self._generate_dual_pane_flow()
        self._generate_monitor_wall()
        self._generate_command_center()
        self._generate_utils()

    def _generate_focus_metric(self) -> None:
        """Generate FocusMetric archetype component."""
        content = '''/**
 * FocusMetric Archetype
 *
 * Single dominant KPI with supporting context.
 * Best for: Dashboards with one critical metric (uptime, revenue, alerts)
 */

import { LayoutPlan, AttentionSignal } from '@/types/layout';
import { SignalRenderer } from '../signals/SignalRenderer';

interface FocusMetricProps {
  plan: LayoutPlan;
  signals: Record<string, AttentionSignal>;
  signalData: Record<string, unknown>;
}

export function FocusMetric({ plan, signals, signalData }: FocusMetricProps) {
  // Find hero and context surfaces
  const heroSurface = plan.surfaces.find(s => s.id === 'hero');
  const contextSurface = plan.surfaces.find(s => s.id === 'context');

  return (
    <main className="focus-metric min-h-screen p-4 sm:p-6 lg:p-8 bg-gradient-to-br from-blue-50 to-indigo-50" role="main" aria-label="Focus metric dashboard">
      {/* Hero Section - Large, Prominent */}
      {heroSurface && (
        <section className="hero-section mb-6 sm:mb-8" aria-label="Primary metric">
          <div className="bg-white rounded-xl sm:rounded-2xl shadow-xl p-6 sm:p-8 lg:p-12 border border-gray-100">
            {heroSurface.assigned_signals.map(signalId => {
              const signal = signals[signalId];
              if (!signal) return null;

              return (
                <SignalRenderer
                  key={signalId}
                  signal={signal}
                  data={signalData[signalId]}
                  variant="hero"
                />
              );
            })}
          </div>
        </section>
      )}

      {/* Context Section - Supporting Information */}
      {contextSurface && contextSurface.assigned_signals.length > 0 && (
        <section className="context-section" aria-label="Supporting metrics">
          <div className="bg-white rounded-lg shadow-md p-4 sm:p-6 border border-gray-100">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-4" role="list" aria-label="Context metrics">
              {contextSurface.assigned_signals.map(signalId => {
                const signal = signals[signalId];
                if (!signal) return null;

                return (
                  <div key={signalId} role="listitem">
                    <SignalRenderer
                      signal={signal}
                      data={signalData[signalId]}
                      variant="context"
                    />
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      )}
    </main>
  );
}
'''
        output_dir = self.project_path / "src" / "components" / "archetypes"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "FocusMetric.tsx"
        output_path.write_text(content)

    def _generate_scanner_table(self) -> None:
        """Generate ScannerTable archetype component."""
        content = '''/**
 * ScannerTable Archetype
 *
 * Dense, scannable table for rapid review.
 * Best for: Admin panels, data review, list processing
 */

import { LayoutPlan, AttentionSignal } from '@/types/layout';
import { SignalRenderer } from '../signals/SignalRenderer';

interface ScannerTableProps {
  plan: LayoutPlan;
  signals: Record<string, AttentionSignal>;
  signalData: Record<string, unknown>;
}

export function ScannerTable({ plan, signals, signalData }: ScannerTableProps) {
  // Find table and toolbar surfaces
  const tableSurface = plan.surfaces.find(s => s.id === 'table');
  const toolbarSurface = plan.surfaces.find(s => s.id === 'toolbar');

  return (
    <main className="scanner-table min-h-screen p-3 sm:p-4 lg:p-6 bg-gray-50" role="main" aria-label="Data table browser">
      {/* Toolbar - Actions and Filters */}
      {toolbarSurface && toolbarSurface.assigned_signals.length > 0 && (
        <nav className="toolbar-section mb-3 sm:mb-4" aria-label="Table controls and filters">
          <div className="bg-white rounded-lg shadow-sm p-3 sm:p-4 border border-gray-200">
            <div className="flex flex-wrap gap-2 sm:gap-3 lg:gap-4 items-center" role="toolbar">
              {toolbarSurface.assigned_signals.map(signalId => {
                const signal = signals[signalId];
                if (!signal) return null;

                return (
                  <SignalRenderer
                    key={signalId}
                    signal={signal}
                    data={signalData[signalId]}
                    variant="toolbar"
                  />
                );
              })}
            </div>
          </div>
        </nav>
      )}

      {/* Table - Dense, Scannable - Horizontally scrollable on mobile */}
      {tableSurface && (
        <section className="table-section" aria-label="Data table">
          <div className="bg-white rounded-lg shadow-md overflow-x-auto border border-gray-200">
            {tableSurface.assigned_signals.map(signalId => {
              const signal = signals[signalId];
              if (!signal) return null;

              return (
                <SignalRenderer
                  key={signalId}
                  signal={signal}
                  data={signalData[signalId]}
                  variant="table"
                />
              );
            })}
          </div>
        </section>
      )}
    </main>
  );
}
'''
        output_dir = self.project_path / "src" / "components" / "archetypes"
        output_path = output_dir / "ScannerTable.tsx"
        output_path.write_text(content)

    def _generate_dual_pane_flow(self) -> None:
        """Generate DualPaneFlow archetype component."""
        content = '''/**
 * DualPaneFlow Archetype
 *
 * Two-column layout with list navigation and detail view.
 * Best for: Email clients, file browsers, content management
 */

import { LayoutPlan, AttentionSignal } from '@/types/layout';
import { SignalRenderer } from '../signals/SignalRenderer';

interface DualPaneFlowProps {
  plan: LayoutPlan;
  signals: Record<string, AttentionSignal>;
  signalData: Record<string, unknown>;
}

export function DualPaneFlow({ plan, signals, signalData }: DualPaneFlowProps) {
  // Find list and detail surfaces
  const listSurface = plan.surfaces.find(s => s.id === 'list');
  const detailSurface = plan.surfaces.find(s => s.id === 'detail');

  return (
    <div className="dual-pane-flow min-h-screen flex flex-col md:flex-row bg-gray-50" role="main">
      {/* List Pane - Navigation - Stacks on mobile, side-by-side on desktop */}
      {listSurface && (
        <nav className="list-pane w-full md:w-2/5 lg:w-1/3 xl:w-1/4 md:border-r border-b md:border-b-0 border-gray-200 bg-white overflow-y-auto max-h-64 md:max-h-none" aria-label="Item list navigation">
          {listSurface.assigned_signals.map(signalId => {
            const signal = signals[signalId];
            if (!signal) return null;

            return (
              <SignalRenderer
                key={signalId}
                signal={signal}
                data={signalData[signalId]}
                variant="list"
              />
            );
          })}
        </nav>
      )}

      {/* Detail Pane - Content */}
      {detailSurface && (
        <main className="detail-pane flex-1 p-4 sm:p-6 lg:p-8 overflow-y-auto" aria-label="Item detail view">
          <article className="max-w-4xl mx-auto">
            {detailSurface.assigned_signals.map(signalId => {
              const signal = signals[signalId];
              if (!signal) return null;

              return (
                <SignalRenderer
                  key={signalId}
                  signal={signal}
                  data={signalData[signalId]}
                  variant="detail"
                />
              );
            })}
          </article>
        </main>
      )}
    </div>
  );
}
'''
        output_dir = self.project_path / "src" / "components" / "archetypes"
        output_path = output_dir / "DualPaneFlow.tsx"
        output_path.write_text(content)

    def _generate_monitor_wall(self) -> None:
        """Generate MonitorWall archetype component."""
        content = '''/**
 * MonitorWall Archetype
 *
 * Grid of multiple signals for at-a-glance monitoring.
 * Best for: Operations dashboards, analytics, system monitoring
 */

import { LayoutPlan, AttentionSignal } from '@/types/layout';
import { SignalRenderer } from '../signals/SignalRenderer';

interface MonitorWallProps {
  plan: LayoutPlan;
  signals: Record<string, AttentionSignal>;
  signalData: Record<string, unknown>;
}

export function MonitorWall({ plan, signals, signalData }: MonitorWallProps) {
  // Find all surfaces
  const primarySurfaces = plan.surfaces.filter(s => s.id.startsWith('primary'));
  const secondarySurfaces = plan.surfaces.filter(s => s.id.startsWith('secondary'));

  return (
    <main className="monitor-wall min-h-screen p-3 sm:p-4 lg:p-6 bg-gray-50" role="main" aria-label="Monitor wall dashboard">
      <div className="space-y-4 sm:space-y-6">
        {/* Primary Signals - Larger Cards */}
        {primarySurfaces.length > 0 && (
          <section className="primary-section" aria-label="Primary metrics">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 sm:gap-6" role="list">
              {primarySurfaces.map(surface => (
                <div key={surface.id} role="listitem">
                  {surface.assigned_signals.map(signalId => {
                    const signal = signals[signalId];
                    if (!signal) return null;

                    return (
                      <article key={signalId} className="bg-white rounded-lg shadow-md p-4 sm:p-6 border border-gray-200 h-full">
                        <SignalRenderer
                          signal={signal}
                          data={signalData[signalId]}
                          variant="card"
                        />
                      </article>
                    );
                  })}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Secondary Signals - Smaller Cards - 2 cols on mobile, 4 cols on desktop */}
        {secondarySurfaces.length > 0 && (
          <section className="secondary-section" aria-label="Secondary metrics">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3 sm:gap-4" role="list">
              {secondarySurfaces.map(surface => (
                <div key={surface.id} role="listitem">
                  {surface.assigned_signals.map(signalId => {
                    const signal = signals[signalId];
                    if (!signal) return null;

                    return (
                      <article key={signalId} className="bg-white rounded-md shadow-sm p-3 sm:p-4 border border-gray-100">
                        <SignalRenderer
                          signal={signal}
                          data={signalData[signalId]}
                          variant="compact"
                        />
                      </article>
                    );
                  })}
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
'''
        output_dir = self.project_path / "src" / "components" / "archetypes"
        output_path = output_dir / "MonitorWall.tsx"
        output_path.write_text(content)

    def _generate_command_center(self) -> None:
        """Generate CommandCenter archetype component."""
        content = '''/**
 * CommandCenter Archetype
 *
 * High-density expert interface with many controls.
 * Best for: Power users, complex workflows, multi-tasking
 */

import { LayoutPlan, AttentionSignal } from '@/types/layout';
import { SignalRenderer } from '../signals/SignalRenderer';

interface CommandCenterProps {
  plan: LayoutPlan;
  signals: Record<string, AttentionSignal>;
  signalData: Record<string, unknown>;
}

export function CommandCenter({ plan, signals, signalData }: CommandCenterProps) {
  // Find all surfaces
  const mainSurface = plan.surfaces.find(s => s.id === 'main');
  const sidebarSurface = plan.surfaces.find(s => s.id === 'sidebar');
  const toolbeltSurface = plan.surfaces.find(s => s.id === 'toolbelt');
  const statusSurface = plan.surfaces.find(s => s.id === 'status');

  return (
    <div className="command-center h-screen flex flex-col bg-gray-900 text-gray-100" role="main" aria-label="Command center dashboard">
      {/* Toolbelt - Top Actions */}
      {toolbeltSurface && toolbeltSurface.assigned_signals.length > 0 && (
        <header className="toolbelt-section bg-gray-800 border-b border-gray-700 p-2 sm:p-3" aria-label="Quick actions">
          <div className="flex flex-wrap gap-2 sm:gap-3 items-center text-sm sm:text-base" role="toolbar">
            {toolbeltSurface.assigned_signals.map(signalId => {
              const signal = signals[signalId];
              if (!signal) return null;

              return (
                <SignalRenderer
                  key={signalId}
                  signal={signal}
                  data={signalData[signalId]}
                  variant="toolbelt"
                />
              );
            })}
          </div>
        </header>
      )}

      {/* Main Content Area - Stacks sidebar on mobile, side-by-side on desktop */}
      <div className="flex flex-col md:flex-row flex-1 overflow-hidden">
        {/* Sidebar - Navigation/Tools - Collapsible on mobile */}
        {sidebarSurface && sidebarSurface.assigned_signals.length > 0 && (
          <aside className="sidebar-section w-full md:w-56 lg:w-64 bg-gray-800 md:border-r border-b md:border-b-0 border-gray-700 overflow-y-auto p-3 sm:p-4" aria-label="Navigation and tools">
            <nav className="space-y-3 sm:space-y-4">
              {sidebarSurface.assigned_signals.map(signalId => {
                const signal = signals[signalId];
                if (!signal) return null;

                return (
                  <SignalRenderer
                    key={signalId}
                    signal={signal}
                    data={signalData[signalId]}
                    variant="sidebar"
                  />
                );
              })}
            </nav>
          </aside>
        )}

        {/* Main Work Area - Single column on mobile, 2 cols on desktop */}
        {mainSurface && (
          <section className="main-section flex-1 p-3 sm:p-4 lg:p-6 overflow-y-auto" aria-label="Main workspace">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6" role="list">
              {mainSurface.assigned_signals.map(signalId => {
                const signal = signals[signalId];
                if (!signal) return null;

                return (
                  <article key={signalId} className="bg-gray-800 rounded-lg border border-gray-700 p-4 sm:p-6" role="listitem">
                    <SignalRenderer
                      signal={signal}
                      data={signalData[signalId]}
                      variant="panel"
                    />
                  </article>
                );
              })}
            </div>
          </section>
        )}
      </div>

      {/* Status Bar - Bottom - Compact on mobile */}
      {statusSurface && statusSurface.assigned_signals.length > 0 && (
        <footer className="status-section bg-gray-800 border-t border-gray-700 p-2" role="status" aria-label="Status information" aria-live="polite">
          <div className="flex flex-wrap gap-2 sm:gap-4 items-center text-xs sm:text-sm overflow-x-auto">
            {statusSurface.assigned_signals.map(signalId => {
              const signal = signals[signalId];
              if (!signal) return null;

              return (
                <SignalRenderer
                  key={signalId}
                  signal={signal}
                  data={signalData[signalId]}
                  variant="status"
                />
              );
            })}
          </div>
        </footer>
      )}
    </div>
  );
}
'''
        output_dir = self.project_path / "src" / "components" / "archetypes"
        output_path = output_dir / "CommandCenter.tsx"
        output_path.write_text(content)

    def _generate_utils(self) -> None:
        """Generate archetype utility and index file."""
        # Index file
        index_content = '''/**
 * Archetype Components Index
 *
 * Exports all 5 layout archetype components.
 */

export { FocusMetric } from './FocusMetric';
export { ScannerTable } from './ScannerTable';
export { DualPaneFlow } from './DualPaneFlow';
export { MonitorWall } from './MonitorWall';
export { CommandCenter } from './CommandCenter';
'''
        output_dir = self.project_path / "src" / "components" / "archetypes"
        (output_dir / "index.ts").write_text(index_content)

        # ArchetypeRouter - renders correct archetype based on plan
        router_content = '''/**
 * Archetype Router
 *
 * Dynamically renders the correct archetype component based on layout plan.
 */

import { LayoutPlan, LayoutArchetype, AttentionSignal } from '@/types/layout';
import { FocusMetric } from './FocusMetric';
import { ScannerTable } from './ScannerTable';
import { DualPaneFlow } from './DualPaneFlow';
import { MonitorWall } from './MonitorWall';
import { CommandCenter } from './CommandCenter';

interface ArchetypeRouterProps {
  plan: LayoutPlan;
  signals: Record<string, AttentionSignal>;
  signalData: Record<string, unknown>;
}

export function ArchetypeRouter({ plan, signals, signalData }: ArchetypeRouterProps) {
  switch (plan.archetype) {
    case LayoutArchetype.FOCUS_METRIC:
      return <FocusMetric plan={plan} signals={signals} signalData={signalData} />;

    case LayoutArchetype.SCANNER_TABLE:
      return <ScannerTable plan={plan} signals={signals} signalData={signalData} />;

    case LayoutArchetype.DUAL_PANE_FLOW:
      return <DualPaneFlow plan={plan} signals={signals} signalData={signalData} />;

    case LayoutArchetype.MONITOR_WALL:
      return <MonitorWall plan={plan} signals={signals} signalData={signalData} />;

    case LayoutArchetype.COMMAND_CENTER:
      return <CommandCenter plan={plan} signals={signals} signalData={signalData} />;

    default:
      return (
        <div className="p-6">
          <p className="text-red-600">Unknown archetype: {plan.archetype}</p>
        </div>
      );
  }
}
'''
        (output_dir / "ArchetypeRouter.tsx").write_text(router_content)


__all__ = ["ArchetypeComponentsGenerator"]
