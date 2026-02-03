"""
Dashboard routes and templates for Dazzle Control Plane.

Uses HTMX + Alpine.js + DaisyUI (matching Dazzle's frontend stack).
"""

from __future__ import annotations

import html
import json
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .auth import AuthContext, get_auth_context

router = APIRouter(tags=["Dashboard"])


def _base_template(title: str, content: str, user: str = "") -> str:
    """Base HTML template matching Dazzle's stack."""
    return f"""<!DOCTYPE html>
<html lang="en" x-data="{{ darkMode: localStorage.getItem('darkMode') === 'true' }}"
      x-init="$watch('darkMode', val => localStorage.setItem('darkMode', val))"
      :class="{{ 'dark': darkMode }}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>

    <!-- DaisyUI + Tailwind (matching Dazzle) -->
    <link href="https://cdn.jsdelivr.net/npm/daisyui@4.12.14/dist/full.min.css" rel="stylesheet" />
    <script src="https://cdn.tailwindcss.com"></script>

    <!-- HTMX (matching Dazzle) -->
    <script src="https://unpkg.com/htmx.org@2.0.3"></script>
    <script src="https://unpkg.com/htmx-ext-json-enc@2.0.1/json-enc.js"></script>

    <!-- Alpine.js (matching Dazzle) -->
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.3/dist/cdn.min.js"></script>

    <!-- Chart.js for metrics -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

    <script>
        tailwind.config = {{
            darkMode: 'class',
            theme: {{
                extend: {{
                    colors: {{
                        primary: '#4f46e5',
                    }}
                }}
            }}
        }}
    </script>
</head>
<body class="min-h-screen bg-base-200" hx-boost="true">
    <!-- Navbar -->
    <div class="navbar bg-primary text-primary-content shadow-lg">
        <div class="flex-1">
            <a href="/" class="btn btn-ghost text-xl">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                Dazzle Control Plane
            </a>
        </div>
        <div class="flex-none gap-2">
            <div class="badge badge-success gap-2"
                 hx-get="/dashboard/status-badge"
                 hx-trigger="load, every 5s"
                 hx-swap="outerHTML">
                <span class="loading loading-ring loading-xs"></span>
                Connecting...
            </div>
            <div id="clock"
                 hx-get="/dashboard/clock"
                 hx-trigger="load, every 1s"
                 hx-swap="innerHTML"
                 class="font-mono">
                --:--:--
            </div>
            <div class="dropdown dropdown-end" x-data="{{ open: false }}">
                <label tabindex="0" class="btn btn-ghost btn-circle" @click="open = !open">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5.121 17.804A13.937 13.937 0 0112 16c2.5 0 4.847.655 6.879 1.804M15 10a3 3 0 11-6 0 3 3 0 016 0zm6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                </label>
                <ul tabindex="0" class="dropdown-content z-[1] menu p-2 shadow bg-base-100 rounded-box w-52 text-base-content"
                    x-show="open" @click.away="open = false" x-transition>
                    <li class="menu-title"><span>{user or "User"}</span></li>
                    <li>
                        <label class="flex items-center gap-2">
                            <input type="checkbox" class="toggle toggle-sm" x-model="darkMode" />
                            Dark Mode
                        </label>
                    </li>
                    <li><a href="/logout">Logout</a></li>
                </ul>
            </div>
        </div>
    </div>

    <!-- Main Content -->
    <main class="container mx-auto p-4 md:p-6">
        {content}
    </main>

    <!-- Toast container for notifications -->
    <div id="toast-container" class="toast toast-end" x-data="{{ toasts: [] }}">
        <template x-for="toast in toasts" :key="toast.id">
            <div class="alert" :class="toast.type" x-transition>
                <span x-text="toast.message"></span>
            </div>
        </template>
    </div>

    <!-- Detail Modal -->
    <dialog id="detail-modal" class="modal">
        <div class="modal-box w-11/12 max-w-5xl">
            <form method="dialog">
                <button class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2">X</button>
            </form>
            <h3 class="font-bold text-lg" id="modal-title">Details</h3>
            <div id="modal-content" class="py-4">
                <span class="loading loading-spinner loading-lg"></span>
            </div>
        </div>
        <form method="dialog" class="modal-backdrop">
            <button>close</button>
        </form>
    </dialog>

    <script>
        function showModal(title, contentUrl) {{
            document.getElementById('modal-title').textContent = title;
            document.getElementById('modal-content').innerHTML = '<span class="loading loading-spinner loading-lg"></span>';
            document.getElementById('detail-modal').showModal();
            htmx.ajax('GET', contentUrl, '#modal-content');
        }}
    </script>
</body>
</html>"""


def _dashboard_content() -> str:
    """Dashboard page content."""
    return """
    <!-- Stats Cards -->
    <div id="stats-cards"
         hx-get="/dashboard/stats"
         hx-trigger="load, every 5s"
         hx-swap="innerHTML"
         class="stats stats-vertical lg:stats-horizontal shadow w-full mb-6 bg-base-100">
        <div class="stat animate-pulse">
            <div class="stat-title">Loading...</div>
            <div class="stat-value">--</div>
        </div>
    </div>

    <!-- Charts Row -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
                <h2 class="card-title">Request Rate</h2>
                <canvas id="requests-chart" height="200"></canvas>
            </div>
        </div>
        <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
                <h2 class="card-title">Response Latency</h2>
                <canvas id="latency-chart" height="200"></canvas>
            </div>
        </div>
    </div>

    <!-- Tabs for different views -->
    <div x-data="{ activeTab: 'logs' }" class="mb-6">
        <div class="tabs tabs-boxed bg-base-100 p-2 mb-4">
            <a class="tab" :class="{ 'tab-active': activeTab === 'logs' }"
               @click="activeTab = 'logs'">Logs</a>
            <a class="tab" :class="{ 'tab-active': activeTab === 'processes' }"
               @click="activeTab = 'processes'">Processes</a>
            <a class="tab" :class="{ 'tab-active': activeTab === 'metrics' }"
               @click="activeTab = 'metrics'">Metrics</a>
        </div>

        <!-- Logs Panel -->
        <div x-show="activeTab === 'logs'" x-transition class="card bg-base-100 shadow-xl">
            <div class="card-body">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="card-title">Recent Logs</h2>
                    <select id="log-level" class="select select-bordered select-sm"
                            hx-get="/dashboard/logs"
                            hx-trigger="change"
                            hx-target="#logs-container"
                            hx-include="this">
                        <option value="all">All Levels</option>
                        <option value="error">Errors Only</option>
                        <option value="warning">Warnings</option>
                        <option value="info" selected>Info</option>
                    </select>
                </div>
                <div id="logs-container"
                     hx-get="/dashboard/logs?level=info"
                     hx-trigger="load, every 10s"
                     hx-swap="innerHTML"
                     class="overflow-x-auto">
                    <div class="flex justify-center py-8">
                        <span class="loading loading-spinner loading-lg"></span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Processes Panel -->
        <div x-show="activeTab === 'processes'" x-transition class="card bg-base-100 shadow-xl">
            <div class="card-body">
                <h2 class="card-title">Active Processes</h2>
                <div id="processes-container"
                     hx-get="/dashboard/processes"
                     hx-trigger="load, every 10s"
                     hx-swap="innerHTML">
                    <div class="flex justify-center py-8">
                        <span class="loading loading-spinner loading-lg"></span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Metrics Panel -->
        <div x-show="activeTab === 'metrics'" x-transition class="card bg-base-100 shadow-xl">
            <div class="card-body">
                <h2 class="card-title">Available Metrics</h2>
                <div id="metrics-container"
                     hx-get="/dashboard/metrics-list"
                     hx-trigger="load"
                     hx-swap="innerHTML">
                    <div class="flex justify-center py-8">
                        <span class="loading loading-spinner loading-lg"></span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Chart initialization script -->
    <script>
        let requestsChart, latencyChart;

        function initCharts() {
            const requestsCtx = document.getElementById('requests-chart');
            const latencyCtx = document.getElementById('latency-chart');

            if (!requestsCtx || !latencyCtx) return;

            const chartConfig = {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { display: true, grid: { display: false } },
                    y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.1)' } }
                },
                plugins: {
                    legend: { display: false }
                },
                elements: {
                    line: { tension: 0.3 },
                    point: { radius: 2 }
                }
            };

            requestsChart = new Chart(requestsCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Requests/min',
                        data: [],
                        borderColor: 'oklch(var(--p))',
                        backgroundColor: 'oklch(var(--p) / 0.1)',
                        fill: true,
                    }]
                },
                options: chartConfig
            });

            latencyChart = new Chart(latencyCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Latency (ms)',
                        data: [],
                        borderColor: 'oklch(var(--a))',
                        backgroundColor: 'oklch(var(--a) / 0.1)',
                        fill: true,
                    }]
                },
                options: chartConfig
            });
        }

        async function updateCharts() {
            try {
                const response = await fetch('/api/dashboard/data');
                const data = await response.json();

                if (requestsChart && data.charts.requests.length > 0) {
                    requestsChart.data.labels = data.charts.requests.map(p =>
                        new Date(p.ts * 1000).toLocaleTimeString('en-GB', {hour: '2-digit', minute:'2-digit'})
                    );
                    requestsChart.data.datasets[0].data = data.charts.requests.map(p => p.value);
                    requestsChart.update('none');
                }

                if (latencyChart && data.charts.latency.length > 0) {
                    latencyChart.data.labels = data.charts.latency.map(p =>
                        new Date(p.ts * 1000).toLocaleTimeString('en-GB', {hour: '2-digit', minute:'2-digit'})
                    );
                    latencyChart.data.datasets[0].data = data.charts.latency.map(p => p.value);
                    latencyChart.update('none');
                }
            } catch (e) {
                console.error('Failed to update charts:', e);
            }
        }

        document.addEventListener('DOMContentLoaded', () => {
            initCharts();
            updateCharts();
            setInterval(updateCharts, 30000);
        });
    </script>
    """


def _login_page() -> str:
    """Login page template."""
    return """<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Dazzle Control Plane</title>
    <link href="https://cdn.jsdelivr.net/npm/daisyui@4.12.14/dist/full.min.css" rel="stylesheet" />
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@2.0.3"></script>
</head>
<body class="min-h-screen bg-base-200 flex items-center justify-center">
    <div class="card w-96 bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title justify-center text-2xl mb-4">Dazzle Control Plane</h2>
            <form hx-post="/login" hx-target="body" hx-swap="innerHTML">
                <div class="form-control mb-4">
                    <label class="label">
                        <span class="label-text">Username</span>
                    </label>
                    <input type="text" name="username" placeholder="admin"
                           class="input input-bordered" required autofocus />
                </div>
                <div class="form-control mb-6">
                    <label class="label">
                        <span class="label-text">Password</span>
                    </label>
                    <input type="password" name="password" placeholder="********"
                           class="input input-bordered" required />
                </div>
                <div class="form-control">
                    <button type="submit" class="btn btn-primary">Login</button>
                </div>
            </form>
        </div>
    </div>
</body>
</html>"""


# ============================================================================
# Routes
# ============================================================================


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> str:
    """Render the main dashboard."""
    content = _dashboard_content()
    return _base_template("Dazzle Control Plane", content, auth.username)


@router.get("/login", response_class=HTMLResponse)
async def login_page() -> str:
    """Render login page."""
    return _login_page()


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request) -> HTMLResponse | RedirectResponse:
    """Handle login form submission."""
    import hmac

    from .auth import CONTROL_PLANE_PASSWORD, CONTROL_PLANE_USERNAME, create_session

    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    # Verify credentials
    username_valid = hmac.compare_digest(str(username), CONTROL_PLANE_USERNAME)
    password_valid = (
        hmac.compare_digest(str(password), CONTROL_PLANE_PASSWORD)
        if CONTROL_PLANE_PASSWORD
        else True
    )

    if username_valid and password_valid:
        # Create session and redirect
        session_token = create_session()
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key="control_session",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=86400,
        )
        return response

    # Invalid credentials - show error
    return HTMLResponse(
        content="""<!DOCTYPE html>
<html><head>
<link href="https://cdn.jsdelivr.net/npm/daisyui@4.12.14/dist/full.min.css" rel="stylesheet" />
<script src="https://cdn.tailwindcss.com"></script>
</head><body class="min-h-screen bg-base-200 flex items-center justify-center">
<div class="card w-96 bg-base-100 shadow-xl">
<div class="card-body">
<div class="alert alert-error mb-4"><span>Invalid credentials</span></div>
<a href="/login" class="btn btn-primary">Try Again</a>
</div></div></body></html>"""
    )


@router.get("/logout", response_class=HTMLResponse)
async def logout(request: Request) -> RedirectResponse:
    """Handle logout."""
    from .auth import invalidate_session

    session_token = request.cookies.get("control_session")
    if session_token:
        invalidate_session(session_token)

    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("control_session")
    return response


# ============================================================================
# HTMX Partials
# ============================================================================


@router.get("/dashboard/clock", response_class=HTMLResponse)
async def clock() -> str:
    """Return current time for the clock display."""
    return datetime.now().strftime("%H:%M:%S")


@router.get("/dashboard/status-badge", response_class=HTMLResponse)
async def status_badge(request: Request) -> str:
    """Return status badge."""
    try:
        store = request.app.state.metrics_collector.store
        err_count = store.get_summary("http_errors_total", duration_seconds=300).get("count", 0)

        if err_count > 10:
            return '<div class="badge badge-error gap-2">Issues Detected</div>'
        elif err_count > 0:
            return f'<div class="badge badge-warning gap-2">{err_count} Errors</div>'
        return '<div class="badge badge-success gap-2">Healthy</div>'
    except Exception:
        return '<div class="badge badge-ghost gap-2">Unknown</div>'


@router.get("/dashboard/stats", response_class=HTMLResponse)
async def stats_cards(request: Request) -> str:
    """Render stats cards."""
    try:
        store = request.app.state.metrics_collector.store

        req_summary = store.get_summary("http_requests_total", duration_seconds=60)
        err_summary = store.get_summary("http_errors_total", duration_seconds=60)
        lat_summary = store.get_summary("http_latency_ms", duration_seconds=60)

        requests_count = req_summary.get("count", 0)
        error_count = err_summary.get("count", 0)
        error_pct = (error_count / requests_count * 100) if requests_count > 0 else 0
        latency_avg = lat_summary.get("avg") or 0
        latency_max = lat_summary.get("max") or 0

        # Determine status
        if error_pct > 5:
            status_class = "text-error"
            status_text = "Degraded"
        elif error_pct > 1:
            status_class = "text-warning"
            status_text = "Warning"
        else:
            status_class = "text-success"
            status_text = "OK"

        return f"""
        <div class="stat cursor-pointer hover:bg-base-200 transition-colors"
             onclick="showModal('Health Status', '/dashboard/detail/health')">
            <div class="stat-figure {status_class}">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
            </div>
            <div class="stat-title">Health</div>
            <div class="stat-value {status_class}">{status_text}</div>
            <div class="stat-desc">{error_count} errors in last minute</div>
        </div>
        <div class="stat cursor-pointer hover:bg-base-200 transition-colors"
             onclick="showModal('Request Details', '/dashboard/detail/requests')">
            <div class="stat-figure text-primary">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                </svg>
            </div>
            <div class="stat-title">Requests/min</div>
            <div class="stat-value text-primary">{requests_count:,.0f}</div>
            <div class="stat-desc">Last 60 seconds</div>
        </div>
        <div class="stat cursor-pointer hover:bg-base-200 transition-colors"
             onclick="showModal('Latency Details', '/dashboard/detail/latency')">
            <div class="stat-figure text-secondary">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
            </div>
            <div class="stat-title">Avg Latency</div>
            <div class="stat-value text-secondary">{latency_avg:.0f}ms</div>
            <div class="stat-desc">P99: {latency_max:.0f}ms</div>
        </div>
        <div class="stat cursor-pointer hover:bg-base-200 transition-colors"
             onclick="showModal('Error Details', '/dashboard/detail/errors')">
            <div class="stat-figure text-accent">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
            </div>
            <div class="stat-title">Error Rate</div>
            <div class="stat-value text-accent">{error_pct:.1f}%</div>
            <div class="stat-desc">Target: &lt; 1%</div>
        </div>
        """
    except Exception:
        return """
        <div class="stat">
            <div class="stat-title">Status</div>
            <div class="stat-value text-warning">No Data</div>
            <div class="stat-desc">Waiting for metrics...</div>
        </div>
        """


@router.get("/dashboard/logs", response_class=HTMLResponse)
async def logs_list(request: Request, level: str = "info") -> str:
    """Render recent logs."""
    try:
        log_store = request.app.state.log_store
        log_level = level.lower() if level and level != "all" else None
        entries = log_store.get_recent(count=100, level=log_level)

        if not entries:
            return """
            <div class="text-center py-8 text-base-content/60">
                <p>No logs available</p>
            </div>
            """

        rows = []
        for i, entry in enumerate(entries):
            ts = datetime.fromtimestamp(entry.timestamp).strftime("%H:%M:%S")
            full_ts = datetime.fromtimestamp(entry.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            level_badge = {
                "ERROR": "badge-error",
                "WARNING": "badge-warning",
                "INFO": "badge-info",
                "DEBUG": "badge-ghost",
            }.get(entry.level, "badge-ghost")

            safe_message = html.escape(entry.message[:150])
            full_message = html.escape(entry.message)
            is_truncated = len(entry.message) > 150
            if is_truncated:
                safe_message += "..."

            row_id = f"log-row-{i}"
            expand_btn = (
                f"""<button class="btn btn-ghost btn-xs" onclick="event.stopPropagation(); document.getElementById('{row_id}-detail').classList.toggle('hidden')">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
            </button>"""
                if is_truncated or entry.level == "ERROR"
                else ""
            )

            rows.append(f"""
            <tr class="hover cursor-pointer" id="{row_id}" onclick="document.getElementById('{row_id}-detail').classList.toggle('hidden')">
                <td class="font-mono text-sm">{ts}</td>
                <td><span class="badge {level_badge} badge-sm">{entry.level}</span></td>
                <td class="text-sm opacity-70">{html.escape(entry.source)}</td>
                <td class="text-sm max-w-md truncate">{safe_message}</td>
                <td>{expand_btn}</td>
            </tr>
            <tr id="{row_id}-detail" class="hidden bg-base-200">
                <td colspan="5" class="p-4">
                    <div class="text-xs opacity-60 mb-2">{full_ts} | {html.escape(entry.source)}</div>
                    <pre class="whitespace-pre-wrap text-sm font-mono bg-base-300 p-3 rounded-lg overflow-x-auto max-h-64">{full_message}</pre>
                </td>
            </tr>
            """)

        return f"""
        <table class="table table-sm">
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Level</th>
                    <th>Source</th>
                    <th>Message</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows)}
            </tbody>
        </table>
        <div class="text-xs opacity-50 mt-2">Click any row to expand details</div>
        """

    except Exception as e:
        return f"""
        <div class="alert alert-error">
            <span>Error loading logs: {html.escape(str(e))}</span>
        </div>
        """


@router.get("/dashboard/processes", response_class=HTMLResponse)
async def processes_list(request: Request) -> str:
    """Render active processes list."""
    try:
        monitor = request.app.state.process_monitor
        stats = monitor.get_stats()
        active_runs = monitor.get_active_runs()
        pending_tasks = monitor.get_pending_tasks(count=10)

        # If no processes at all, show empty state
        if stats.total_runs == 0 and not pending_tasks:
            return """
            <div class="text-center py-8 text-base-content/60">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 mx-auto mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                </svg>
                <p>No processes found</p>
                <p class="text-sm mt-2">Start a process to see it here</p>
            </div>
            """

        # Build stats row
        stats_html = f"""
        <div class="stats stats-horizontal bg-base-200 w-full mb-4">
            <div class="stat">
                <div class="stat-title">Running</div>
                <div class="stat-value text-primary">{stats.running}</div>
            </div>
            <div class="stat">
                <div class="stat-title">Waiting</div>
                <div class="stat-value text-warning">{stats.waiting}</div>
            </div>
            <div class="stat">
                <div class="stat-title">Completed</div>
                <div class="stat-value text-success">{stats.completed}</div>
            </div>
            <div class="stat">
                <div class="stat-title">Failed</div>
                <div class="stat-value text-error">{stats.failed}</div>
            </div>
        </div>
        """

        # Build active runs table
        runs_html = ""
        if active_runs:
            rows = []
            for run in active_runs[:20]:
                status_badge = {
                    "running": "badge-primary",
                    "waiting": "badge-warning",
                    "pending": "badge-ghost",
                    "completed": "badge-success",
                    "failed": "badge-error",
                }.get(run.status, "badge-ghost")

                ts = (
                    datetime.fromtimestamp(run.started_at).strftime("%H:%M:%S")
                    if run.started_at
                    else "-"
                )
                step = html.escape(run.current_step or "-")
                duration = run.duration_str

                rows.append(f"""
                <tr class="hover">
                    <td class="font-mono text-sm">{html.escape(run.id[:8])}</td>
                    <td>{html.escape(run.process_name)}</td>
                    <td><span class="badge {status_badge} badge-sm">{run.status}</span></td>
                    <td class="text-sm">{step}</td>
                    <td class="text-sm">{ts}</td>
                    <td class="text-sm">{duration}</td>
                </tr>
                """)

            runs_html = f"""
            <h3 class="font-semibold mb-2 mt-4">Active Runs</h3>
            <table class="table table-sm">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Process</th>
                        <th>Status</th>
                        <th>Current Step</th>
                        <th>Started</th>
                        <th>Duration</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows)}
                </tbody>
            </table>
            """

        # Build pending human tasks table
        tasks_html = ""
        if pending_tasks:
            task_rows = []
            for task in pending_tasks:
                overdue_class = "text-error" if task.is_overdue else ""
                due_str = (
                    datetime.fromtimestamp(task.due_at).strftime("%H:%M") if task.due_at else "-"
                )
                assignee = html.escape(task.assignee or "Unassigned")

                task_rows.append(f"""
                <tr class="hover {overdue_class}">
                    <td class="font-mono text-sm">{html.escape(task.id[:8])}</td>
                    <td>{html.escape(task.task_type)}</td>
                    <td>{assignee}</td>
                    <td class="text-sm">{due_str}</td>
                </tr>
                """)

            overdue_badge = (
                f'<span class="badge badge-error badge-sm ml-2">{stats.overdue_tasks} overdue</span>'
                if stats.overdue_tasks > 0
                else ""
            )
            tasks_html = f"""
            <h3 class="font-semibold mb-2 mt-4">Pending Human Tasks {overdue_badge}</h3>
            <table class="table table-sm">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Type</th>
                        <th>Assignee</th>
                        <th>Due</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(task_rows)}
                </tbody>
            </table>
            """

        return stats_html + runs_html + tasks_html

    except Exception as e:
        return f"""
        <div class="alert alert-error">
            <span>Error loading processes: {html.escape(str(e))}</span>
        </div>
        """


@router.get("/dashboard/metrics-list", response_class=HTMLResponse)
async def metrics_list(request: Request) -> str:
    """Render list of available metrics."""
    try:
        store = request.app.state.metrics_collector.store
        metric_names = store.get_metric_names()

        if not metric_names:
            return """
            <div class="text-center py-8 text-base-content/60">
                <p>No metrics collected yet</p>
            </div>
            """

        rows = []
        for name in metric_names:
            summary = store.get_summary(name, duration_seconds=300)
            safe_name = html.escape(name)
            rows.append(f"""
            <tr class="hover cursor-pointer" onclick="showModal('{safe_name}', '/dashboard/detail/metric/{safe_name}')">
                <td class="font-mono">{safe_name}</td>
                <td>{summary.get("count", 0)}</td>
                <td>{summary.get("avg", 0):.2f}</td>
                <td>{summary.get("min", 0):.2f}</td>
                <td>{summary.get("max", 0):.2f}</td>
                <td>
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                    </svg>
                </td>
            </tr>
            """)

        return f"""
        <table class="table">
            <thead>
                <tr>
                    <th>Metric</th>
                    <th>Count (5m)</th>
                    <th>Avg</th>
                    <th>Min</th>
                    <th>Max</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows)}
            </tbody>
        </table>
        <div class="text-xs opacity-50 mt-2">Click any metric to see detailed chart</div>
        """

    except Exception as e:
        return f"""
        <div class="alert alert-error">
            <span>Error: {html.escape(str(e))}</span>
        </div>
        """


# ============================================================================
# Detail Drill-down Endpoints
# ============================================================================


@router.get("/dashboard/detail/health", response_class=HTMLResponse)
async def detail_health(request: Request) -> str:
    """Health status detail view."""
    try:
        store = request.app.state.metrics_collector.store
        log_store = request.app.state.log_store

        # Get error summary
        err_5m = store.get_summary("http_errors_total", duration_seconds=300)
        err_1h = store.get_summary("http_errors_total", duration_seconds=3600)
        req_5m = store.get_summary("http_requests_total", duration_seconds=300)
        req_1h = store.get_summary("http_requests_total", duration_seconds=3600)

        # Calculate error rates
        err_rate_5m = (
            (err_5m.get("count", 0) / req_5m.get("count", 1) * 100)
            if req_5m.get("count", 0) > 0
            else 0
        )
        err_rate_1h = (
            (err_1h.get("count", 0) / req_1h.get("count", 1) * 100)
            if req_1h.get("count", 0) > 0
            else 0
        )

        # Get recent errors
        recent_errors = log_store.get_recent(count=10, level="error")

        error_rows = ""
        for entry in recent_errors:
            ts = datetime.fromtimestamp(entry.timestamp).strftime("%H:%M:%S")
            msg = html.escape(entry.message[:100])
            if len(entry.message) > 100:
                msg += "..."
            error_rows += f"""
            <tr class="hover">
                <td class="font-mono text-sm">{ts}</td>
                <td class="text-sm">{html.escape(entry.source)}</td>
                <td class="text-sm">{msg}</td>
            </tr>
            """

        err_5m_class = "text-error" if err_rate_5m > 5 else "text-success"
        err_1h_class = "text-error" if err_rate_1h > 5 else "text-success"

        return f"""
        <div class="grid grid-cols-2 gap-4 mb-6">
            <div class="stat bg-base-200 rounded-lg">
                <div class="stat-title">Error Rate (5m)</div>
                <div class="stat-value {err_5m_class}">{err_rate_5m:.2f}%</div>
                <div class="stat-desc">{err_5m.get("count", 0)} errors / {
            req_5m.get("count", 0)
        } requests</div>
            </div>
            <div class="stat bg-base-200 rounded-lg">
                <div class="stat-title">Error Rate (1h)</div>
                <div class="stat-value {err_1h_class}">{err_rate_1h:.2f}%</div>
                <div class="stat-desc">{err_1h.get("count", 0)} errors / {
            req_1h.get("count", 0)
        } requests</div>
            </div>
        </div>

        <h4 class="font-semibold mb-2">Recent Errors</h4>
        {
            f'''<table class="table table-sm">
            <thead>
                <tr><th>Time</th><th>Source</th><th>Message</th></tr>
            </thead>
            <tbody>{error_rows}</tbody>
        </table>'''
            if error_rows
            else '<div class="text-center py-4 opacity-60">No recent errors</div>'
        }
        """
    except Exception as e:
        return f'<div class="alert alert-error">Error: {html.escape(str(e))}</div>'


@router.get("/dashboard/detail/errors", response_class=HTMLResponse)
async def detail_errors(request: Request) -> str:
    """Detailed error view."""
    try:
        log_store = request.app.state.log_store
        errors = log_store.get_recent(count=50, level="error")

        if not errors:
            return '<div class="text-center py-8 opacity-60">No errors recorded</div>'

        rows = []
        for _i, entry in enumerate(errors):
            ts = datetime.fromtimestamp(entry.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            msg_short = html.escape(entry.message[:80])
            if len(entry.message) > 80:
                msg_short += "..."
            rows.append(f"""
            <div class="collapse collapse-arrow bg-base-200 mb-2">
                <input type="checkbox" />
                <div class="collapse-title">
                    <span class="badge badge-error badge-sm mr-2">ERROR</span>
                    <span class="font-mono text-sm">{ts}</span>
                    <span class="text-sm ml-2 opacity-70">{html.escape(entry.source)}</span>
                    <div class="text-sm truncate mt-1">{msg_short}</div>
                </div>
                <div class="collapse-content">
                    <pre class="whitespace-pre-wrap text-sm font-mono bg-base-300 p-4 rounded-lg overflow-x-auto">{html.escape(entry.message)}</pre>
                </div>
            </div>
            """)

        return f"""
        <div class="max-h-96 overflow-y-auto">
            {"".join(rows)}
        </div>
        <div class="text-xs opacity-50 mt-4">Showing {len(errors)} most recent errors</div>
        """
    except Exception as e:
        return f'<div class="alert alert-error">Error: {html.escape(str(e))}</div>'


@router.get("/dashboard/detail/requests", response_class=HTMLResponse)
async def detail_requests(request: Request) -> str:
    """Request rate detail view with chart."""
    try:
        store = request.app.state.metrics_collector.store
        now = time.time()

        # Get summaries for different time ranges
        req_1m = store.get_summary("http_requests_total", duration_seconds=60)
        req_5m = store.get_summary("http_requests_total", duration_seconds=300)
        req_1h = store.get_summary("http_requests_total", duration_seconds=3600)

        # Get time series data
        series = store.query("http_requests_total", start=now - 3600, end=now)
        chart_data = [{"ts": p.timestamp, "value": p.value} for p in series.points]

        return f"""
        <div class="grid grid-cols-3 gap-4 mb-6">
            <div class="stat bg-base-200 rounded-lg">
                <div class="stat-title">Last Minute</div>
                <div class="stat-value text-primary">{req_1m.get("count", 0)}</div>
            </div>
            <div class="stat bg-base-200 rounded-lg">
                <div class="stat-title">Last 5 Minutes</div>
                <div class="stat-value">{req_5m.get("count", 0)}</div>
            </div>
            <div class="stat bg-base-200 rounded-lg">
                <div class="stat-title">Last Hour</div>
                <div class="stat-value">{req_1h.get("count", 0)}</div>
            </div>
        </div>

        <div class="h-64">
            <canvas id="detail-requests-chart"></canvas>
        </div>

        <script>
            (function() {{
                const data = {json.dumps(chart_data)};
                const ctx = document.getElementById('detail-requests-chart');
                new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: data.map(p => new Date(p.ts * 1000).toLocaleTimeString('en-GB', {{hour: '2-digit', minute:'2-digit'}})),
                        datasets: [{{
                            label: 'Requests',
                            data: data.map(p => p.value),
                            borderColor: 'oklch(var(--p))',
                            backgroundColor: 'oklch(var(--p) / 0.1)',
                            fill: true,
                            tension: 0.3
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{ legend: {{ display: false }} }},
                        scales: {{
                            y: {{ beginAtZero: true }}
                        }}
                    }}
                }});
            }})();
        </script>
        """
    except Exception as e:
        return f'<div class="alert alert-error">Error: {html.escape(str(e))}</div>'


@router.get("/dashboard/detail/latency", response_class=HTMLResponse)
async def detail_latency(request: Request) -> str:
    """Latency detail view with chart."""
    try:
        store = request.app.state.metrics_collector.store
        now = time.time()

        # Get summaries
        lat_5m = store.get_summary("http_latency_ms", duration_seconds=300)
        lat_1h = store.get_summary("http_latency_ms", duration_seconds=3600)

        # Get time series
        series = store.query("http_latency_ms", start=now - 3600, end=now)
        chart_data = [{"ts": p.timestamp, "value": p.value} for p in series.points]

        return f"""
        <div class="grid grid-cols-2 gap-4 mb-6">
            <div class="stat bg-base-200 rounded-lg">
                <div class="stat-title">Last 5 Minutes</div>
                <div class="stat-value text-secondary">{lat_5m.get("avg", 0):.0f}ms</div>
                <div class="stat-desc">Min: {lat_5m.get("min", 0):.0f}ms / Max: {lat_5m.get("max", 0):.0f}ms</div>
            </div>
            <div class="stat bg-base-200 rounded-lg">
                <div class="stat-title">Last Hour</div>
                <div class="stat-value">{lat_1h.get("avg", 0):.0f}ms</div>
                <div class="stat-desc">Min: {lat_1h.get("min", 0):.0f}ms / Max: {lat_1h.get("max", 0):.0f}ms</div>
            </div>
        </div>

        <div class="h-64">
            <canvas id="detail-latency-chart"></canvas>
        </div>

        <script>
            (function() {{
                const data = {json.dumps(chart_data)};
                const ctx = document.getElementById('detail-latency-chart');
                new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: data.map(p => new Date(p.ts * 1000).toLocaleTimeString('en-GB', {{hour: '2-digit', minute:'2-digit'}})),
                        datasets: [{{
                            label: 'Latency (ms)',
                            data: data.map(p => p.value),
                            borderColor: 'oklch(var(--s))',
                            backgroundColor: 'oklch(var(--s) / 0.1)',
                            fill: true,
                            tension: 0.3
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{ legend: {{ display: false }} }},
                        scales: {{
                            y: {{ beginAtZero: true }}
                        }}
                    }}
                }});
            }})();
        </script>
        """
    except Exception as e:
        return f'<div class="alert alert-error">Error: {html.escape(str(e))}</div>'


@router.get("/dashboard/detail/metric/{metric_name:path}", response_class=HTMLResponse)
async def detail_metric(request: Request, metric_name: str) -> str:
    """Detail view for any metric with chart."""
    try:
        store = request.app.state.metrics_collector.store
        now = time.time()

        # Get summaries for different time ranges
        sum_5m = store.get_summary(metric_name, duration_seconds=300)
        sum_1h = store.get_summary(metric_name, duration_seconds=3600)

        # Get time series
        series = store.query(metric_name, start=now - 3600, end=now)
        chart_data = [{"ts": p.timestamp, "value": p.value} for p in series.points]

        safe_name = html.escape(metric_name)

        return f"""
        <div class="grid grid-cols-2 gap-4 mb-6">
            <div class="stat bg-base-200 rounded-lg">
                <div class="stat-title">Last 5 Minutes</div>
                <div class="stat-value">{sum_5m.get("count", 0)}</div>
                <div class="stat-desc">Avg: {sum_5m.get("avg", 0):.2f} | Min: {sum_5m.get("min", 0):.2f} | Max: {sum_5m.get("max", 0):.2f}</div>
            </div>
            <div class="stat bg-base-200 rounded-lg">
                <div class="stat-title">Last Hour</div>
                <div class="stat-value">{sum_1h.get("count", 0)}</div>
                <div class="stat-desc">Avg: {sum_1h.get("avg", 0):.2f} | Min: {sum_1h.get("min", 0):.2f} | Max: {sum_1h.get("max", 0):.2f}</div>
            </div>
        </div>

        <div class="h-64">
            <canvas id="detail-metric-chart"></canvas>
        </div>

        <script>
            (function() {{
                const data = {json.dumps(chart_data)};
                const ctx = document.getElementById('detail-metric-chart');
                new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: data.map(p => new Date(p.ts * 1000).toLocaleTimeString('en-GB', {{hour: '2-digit', minute:'2-digit'}})),
                        datasets: [{{
                            label: '{safe_name}',
                            data: data.map(p => p.value),
                            borderColor: 'oklch(var(--a))',
                            backgroundColor: 'oklch(var(--a) / 0.1)',
                            fill: true,
                            tension: 0.3
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{ legend: {{ display: false }} }},
                        scales: {{
                            y: {{ beginAtZero: true }}
                        }}
                    }}
                }});
            }})();
        </script>
        """
    except Exception as e:
        return f'<div class="alert alert-error">Error: {html.escape(str(e))}</div>'
