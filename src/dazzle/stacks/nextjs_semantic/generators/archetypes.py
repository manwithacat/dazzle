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
 *
 * Performance optimizations:
 * - React.memo prevents unnecessary re-renders
 * - useMemo caches expensive surface lookups
 */

import { memo, useMemo } from 'react';
import { LayoutPlan, AttentionSignal } from '@/types/layout';
import { SignalRenderer } from '../signals/SignalRenderer';

interface FocusMetricProps {
  plan: LayoutPlan;
  signals: Record<string, AttentionSignal>;
  signalData: Record<string, unknown>;
}

export const FocusMetric = memo(function FocusMetric({ plan, signals, signalData }: FocusMetricProps) {
  // Find hero and context surfaces (memoized to avoid repeated lookups)
  const heroSurface = useMemo(() => plan.surfaces.find(s => s.id === 'hero'), [plan.surfaces]);
  const contextSurface = useMemo(() => plan.surfaces.find(s => s.id === 'context'), [plan.surfaces]);

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
});
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
 *
 * Performance optimizations:
 * - React.memo prevents unnecessary re-renders
 * - useMemo caches expensive surface lookups
 */

import { memo, useMemo } from 'react';
import { LayoutPlan, AttentionSignal } from '@/types/layout';
import { SignalRenderer } from '../signals/SignalRenderer';

interface ScannerTableProps {
  plan: LayoutPlan;
  signals: Record<string, AttentionSignal>;
  signalData: Record<string, unknown>;
}

export const ScannerTable = memo(function ScannerTable({ plan, signals, signalData }: ScannerTableProps) {
  // Find table and toolbar surfaces (memoized to avoid repeated lookups)
  const tableSurface = useMemo(() => plan.surfaces.find(s => s.id === 'table'), [plan.surfaces]);
  const toolbarSurface = useMemo(() => plan.surfaces.find(s => s.id === 'toolbar'), [plan.surfaces]);

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

import { memo, useMemo } from 'react';
import { LayoutPlan, AttentionSignal } from '@/types/layout';
import { SignalRenderer } from '../signals/SignalRenderer';

interface DualPaneFlowProps {
  plan: LayoutPlan;
  signals: Record<string, AttentionSignal>;
  signalData: Record<string, unknown>;
}

export const DualPaneFlow = memo(function DualPaneFlow({ plan, signals, signalData }: DualPaneFlowProps) {
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

import { memo, useMemo } from 'react';
import { LayoutPlan, AttentionSignal } from '@/types/layout';
import { SignalRenderer } from '../signals/SignalRenderer';

interface MonitorWallProps {
  plan: LayoutPlan;
  signals: Record<string, AttentionSignal>;
  signalData: Record<string, unknown>;
}

export const MonitorWall = memo(function MonitorWall({ plan, signals, signalData }: MonitorWallProps) {
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
 * Dense, expert-focused dashboard for operations and monitoring.
 * Features real-time alerts, system status grid, and quick actions.
 *
 * Surfaces:
 * - header: Critical alerts and status indicators (priority 3)
 * - main_grid: Dense grid of metrics and charts (priority 1)
 * - left_rail: Quick actions and navigation (priority 2)
 * - right_rail: Contextual information and tools (priority 2)
 *
 * Best for: DevOps, trading, operations centers, system monitoring
 */

import { memo, useMemo, useState } from 'react';
import { LayoutPlan, AttentionSignal } from '@/types/layout';
import { SignalRenderer } from '../signals/SignalRenderer';

interface CommandCenterProps {
  plan: LayoutPlan;
  signals: Record<string, AttentionSignal>;
  signalData: Record<string, unknown>;
}

export const CommandCenter = memo(function CommandCenter({ plan, signals, signalData }: CommandCenterProps) {
  // Memoized surface lookups
  const headerSurface = useMemo(() => plan.surfaces.find(s => s.id === 'header'), [plan.surfaces]);
  const mainGridSurface = useMemo(() => plan.surfaces.find(s => s.id === 'main_grid'), [plan.surfaces]);
  const leftRailSurface = useMemo(() => plan.surfaces.find(s => s.id === 'left_rail'), [plan.surfaces]);
  const rightRailSurface = useMemo(() => plan.surfaces.find(s => s.id === 'right_rail'), [plan.surfaces]);

  // Track alert acknowledgments
  const [acknowledgedAlerts, setAcknowledgedAlerts] = useState<Set<string>>(new Set());

  const acknowledgeAlert = (signalId: string) => {
    setAcknowledgedAlerts(prev => new Set([...prev, signalId]));
  };

  // Separate critical alerts for header
  const criticalSignals = useMemo(() => {
    if (!headerSurface) return [];
    return headerSurface.assigned_signals.filter(id => {
      const signal = signals[id];
      return signal && signal.urgency === 'high';
    });
  }, [headerSurface, signals]);

  const nonCriticalHeaderSignals = useMemo(() => {
    if (!headerSurface) return [];
    return headerSurface.assigned_signals.filter(id => {
      const signal = signals[id];
      return signal && signal.urgency !== 'high';
    });
  }, [headerSurface, signals]);

  return (
    <div className="command-center h-screen flex flex-col bg-gray-900 text-gray-100" role="main" aria-label="Command center dashboard">
      {/* Header - Critical Alerts & Status */}
      {headerSurface && headerSurface.assigned_signals.length > 0 && (
        <header className="header-section bg-gray-800 border-b border-gray-700" aria-label="Alerts and status">
          {/* Critical Alert Banner */}
          {criticalSignals.length > 0 && (
            <div className="bg-red-900/50 border-b border-red-700 px-4 py-2" role="alert" aria-live="assertive">
              <div className="flex items-center gap-4 overflow-x-auto">
                <span className="text-red-400 font-semibold text-sm whitespace-nowrap flex items-center gap-2">
                  <svg className="w-4 h-4 animate-pulse" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                  CRITICAL
                </span>
                {criticalSignals.map(signalId => {
                  const signal = signals[signalId];
                  if (!signal || acknowledgedAlerts.has(signalId)) return null;
                  return (
                    <div key={signalId} className="flex items-center gap-2 text-sm">
                      <SignalRenderer
                        signal={signal}
                        data={signalData[signalId]}
                        variant="alert"
                      />
                      <button
                        onClick={() => acknowledgeAlert(signalId)}
                        className="text-red-400 hover:text-red-300 text-xs underline"
                        aria-label={`Acknowledge ${signal.label}`}
                      >
                        ACK
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Status Indicators */}
          <div className="px-4 py-2 flex items-center gap-4 text-sm overflow-x-auto" role="status">
            {nonCriticalHeaderSignals.map(signalId => {
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
            {/* Timestamp */}
            <div className="ml-auto text-gray-500 text-xs whitespace-nowrap">
              Last updated: {new Date().toLocaleTimeString()}
            </div>
          </div>
        </header>
      )}

      {/* Main Content Area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Rail - Quick Actions */}
        {leftRailSurface && leftRailSurface.assigned_signals.length > 0 && (
          <aside className="left-rail w-48 lg:w-56 bg-gray-800 border-r border-gray-700 overflow-y-auto flex-shrink-0" aria-label="Quick actions">
            <nav className="p-3 space-y-2">
              <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Actions</h2>
              {leftRailSurface.assigned_signals.map(signalId => {
                const signal = signals[signalId];
                if (!signal) return null;
                return (
                  <SignalRenderer
                    key={signalId}
                    signal={signal}
                    data={signalData[signalId]}
                    variant="action"
                  />
                );
              })}
            </nav>
          </aside>
        )}

        {/* Main Grid - Dense Metrics */}
        {mainGridSurface && (
          <section className="main-grid flex-1 p-4 overflow-y-auto" aria-label="Main dashboard">
            <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3" role="list">
              {mainGridSurface.assigned_signals.map(signalId => {
                const signal = signals[signalId];
                if (!signal) return null;
                return (
                  <article
                    key={signalId}
                    className={`
                      bg-gray-800 rounded border border-gray-700 p-3
                      ${signal.urgency === 'high' ? 'border-red-500/50 bg-red-900/10' : ''}
                      ${signal.urgency === 'medium' ? 'border-yellow-500/30' : ''}
                    `}
                    role="listitem"
                  >
                    <SignalRenderer
                      signal={signal}
                      data={signalData[signalId]}
                      variant="compact"
                    />
                  </article>
                );
              })}
            </div>
          </section>
        )}

        {/* Right Rail - Context & Tools */}
        {rightRailSurface && rightRailSurface.assigned_signals.length > 0 && (
          <aside className="right-rail w-56 lg:w-64 bg-gray-800 border-l border-gray-700 overflow-y-auto flex-shrink-0" aria-label="Contextual information">
            <div className="p-3 space-y-4">
              <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Context</h2>
              {rightRailSurface.assigned_signals.map(signalId => {
                const signal = signals[signalId];
                if (!signal) return null;
                return (
                  <div key={signalId} className="border-b border-gray-700 pb-3 last:border-0">
                    <SignalRenderer
                      signal={signal}
                      data={signalData[signalId]}
                      variant="detail"
                    />
                  </div>
                );
              })}
            </div>
          </aside>
        )}
      </div>

      {/* Footer Status Bar */}
      <footer className="bg-gray-800 border-t border-gray-700 px-4 py-1.5 text-xs text-gray-500" role="contentinfo">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-green-500"></span>
              Systems Normal
            </span>
            <span>{plan.surfaces.reduce((sum, s) => sum + s.assigned_signals.length, 0)} signals active</span>
          </div>
          <div className="flex items-center gap-2">
            <kbd className="px-1.5 py-0.5 bg-gray-700 rounded text-gray-400">?</kbd>
            <span>for shortcuts</span>
          </div>
        </div>
      </footer>
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
