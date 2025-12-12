"""
Combined DNR Server - runs both backend and frontend.

Provides a unified development server that:
1. Runs FastAPI backend on port 8000
2. Runs UI dev server on port 3000 with API proxy
3. Handles hot reload for both (when enabled with --watch)
"""

from __future__ import annotations

import http.server
import os
import socketserver
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle.core.strings import to_api_plural
from dazzle_dnr_ui.runtime.js_generator import JSGenerator
from dazzle_dnr_ui.specs import UISpec

if TYPE_CHECKING:
    from dazzle_dnr_back.specs import BackendSpec
    from dazzle_dnr_ui.runtime.hot_reload import HotReloadManager


# =============================================================================
# Terminal Utilities
# =============================================================================


def _supports_hyperlinks() -> bool:
    """
    Check if the terminal likely supports OSC 8 hyperlinks.

    We check for:
    1. NO_COLOR not set (respect user preference)
    2. TERM is set (indicates a terminal environment)
    3. Not running in dumb terminal
    """
    if os.environ.get("NO_COLOR"):
        return False

    term = os.environ.get("TERM", "")
    if not term or term == "dumb":
        return False

    # Most modern terminals support OSC 8: iTerm2, Terminal.app, VS Code, etc.
    return True


def _clickable_url(url: str, label: str | None = None) -> str:
    """
    Create a clickable hyperlink for terminal emulators that support OSC 8.

    Uses the OSC 8 escape sequence format:
    \\e]8;;URL\\e\\\\LABEL\\e]8;;\\e\\\\

    Falls back to plain text if NO_COLOR is set or TERM is not set.
    """
    if not _supports_hyperlinks():
        return label or url

    # OSC 8 hyperlink format
    # \x1b]8;; starts the hyperlink, \x1b\\ (or \x07) ends parameters
    # Then the visible text, then \x1b]8;;\x1b\\ to close
    display = label or url
    return f"\x1b]8;;{url}\x1b\\{display}\x1b]8;;\x1b\\"


# =============================================================================
# Proxy Handler
# =============================================================================


class DNRCombinedHandler(http.server.SimpleHTTPRequestHandler):
    """
    HTTP handler that serves UI and proxies API requests to backend.
    """

    ui_spec: UISpec | None = None
    generator: JSGenerator | None = None
    backend_url: str = "http://127.0.0.1:8000"
    test_mode: bool = False  # Disable hot-reload in test mode for Playwright compatibility
    hot_reload_manager: HotReloadManager | None = None  # For hot reload support
    dev_mode: bool = True  # Enable Dazzle Bar in dev mode (v0.8.5)
    api_route_prefixes: set[str] = set()  # Entity route prefixes (e.g., "/tasks", "/users")

    def _is_api_path(self, path: str) -> bool:
        """Check if a path should be proxied to the backend API."""
        # Known system routes
        if path.startswith(("/auth/", "/files/", "/pages/", "/__test__/")):
            return True
        if path in ("/ui-spec", "/health"):
            return True
        # Entity CRUD routes (dynamically registered)
        for prefix in self.api_route_prefixes:
            if path == prefix or path.startswith(prefix + "/"):
                return True
        return False

    def handle(self) -> None:
        """Handle request, suppressing connection reset errors from browser."""
        try:
            super().handle()
        except ConnectionResetError:
            # Browser closed connection early - common with prefetch/cancelled requests
            pass

    def do_GET(self) -> None:
        """Handle GET requests."""
        path = self.path.split("?")[0]

        # Proxy API requests to backend
        if self._is_api_path(path):
            self._proxy_request("GET")
        elif path.startswith("/dazzle/dev/"):
            # Proxy Dazzle Bar control plane requests (v0.8.5)
            self._proxy_request("GET")
        elif path == "/dazzle-bar.js":
            # Serve Dazzle Bar JavaScript (v0.8.5)
            self._serve_dazzle_bar()
        elif path == "/styles/dnr.css":
            # Serve bundled CSS (v0.8.11)
            self._serve_css()
        elif path == "/dnr-runtime.js":
            self._serve_runtime()
        elif path == "/app.js":
            self._serve_app()
        elif path == "/ui-spec.json":
            self._serve_spec()
        elif path == "/__hot-reload__":
            self._serve_hot_reload()
        elif path == "/docs" or path.startswith("/docs"):
            self._proxy_request("GET")
        elif path == "/openapi.json":
            self._proxy_request("GET")
        else:
            # For SPA: serve HTML for all non-static routes
            # This enables path-based routing (e.g., /task/create, /task/123)
            self._serve_html()

    def do_POST(self) -> None:
        """Handle POST requests."""
        path = self.path.split("?")[0]
        if self._is_api_path(path):
            self._proxy_request("POST")
        elif path.startswith("/dazzle/dev/"):
            # Proxy Dazzle Bar control plane requests (v0.8.5)
            self._proxy_request("POST")
        else:
            self.send_error(405, "Method Not Allowed")

    def do_PUT(self) -> None:
        """Handle PUT requests."""
        path = self.path.split("?")[0]
        if self._is_api_path(path):
            self._proxy_request("PUT")
        else:
            self.send_error(405, "Method Not Allowed")

    def do_DELETE(self) -> None:
        """Handle DELETE requests."""
        path = self.path.split("?")[0]
        if self._is_api_path(path):
            self._proxy_request("DELETE")
        else:
            self.send_error(405, "Method Not Allowed")

    def do_PATCH(self) -> None:
        """Handle PATCH requests."""
        path = self.path.split("?")[0]
        if self._is_api_path(path):
            self._proxy_request("PATCH")
        else:
            self.send_error(405, "Method Not Allowed")

    def do_HEAD(self) -> None:
        """Handle HEAD requests (used by Dazzle Bar to check control plane availability)."""
        if self.path.startswith("/dazzle/dev/"):
            self._proxy_request("HEAD")
        else:
            # Default HEAD behavior for other paths
            super().do_HEAD()

    def _proxy_request(self, method: str) -> None:
        """Proxy request to backend server."""
        try:
            # Build backend URL
            url = f"{self.backend_url}{self.path}"

            # Read request body for non-GET requests
            body = None
            if method in ("POST", "PUT", "PATCH"):
                content_length = int(self.headers.get("Content-Length", 0))
                if content_length > 0:
                    body = self.rfile.read(content_length)

            # Build request
            req = urllib.request.Request(url, data=body, method=method)

            # Copy relevant headers
            for header in ["Content-Type", "Authorization", "Accept"]:
                if self.headers.get(header):
                    req.add_header(header, self.headers[header])

            # Make request
            with urllib.request.urlopen(req, timeout=30) as response:
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(key, value)
                self.end_headers()
                self.wfile.write(response.read())

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            error_body = e.read() if e.fp else b"{}"
            self.wfile.write(error_body)

        except urllib.error.URLError as e:
            self.send_error(502, f"Backend unavailable: {e.reason}")

        except Exception as e:
            self.send_error(500, f"Proxy error: {str(e)}")

    def _serve_html(self) -> None:
        """Serve the main HTML page."""
        if not self.generator:
            self.send_error(500, "No UISpec loaded")
            return

        html = self.generator.generate_html(include_runtime=False)

        # Inject Dazzle Bar script in dev mode (v0.8.5)
        if self.dev_mode:
            dazzle_bar_script = '<script type="module" src="/dazzle-bar.js"></script>\n</body>'
            html = html.replace("</body>", dazzle_bar_script)

        # Inject hot reload script (disabled in test mode for Playwright compatibility)
        if not self.test_mode:
            hot_reload_script = """
<script>
(function() {
  const eventSource = new EventSource('/__hot-reload__');
  eventSource.onmessage = function(e) {
    if (e.data === 'reload') {
      window.location.reload();
    }
  };
})();
</script>
</body>
"""
            html = html.replace("</body>", hot_reload_script)
        # Fix script references - replace inline script placeholders with external references
        html = html.replace(
            "<script>\n\n  </script>\n  <script>",
            '<script src="/dnr-runtime.js"></script>\n  <script src="/app.js"></script>\n  <script>',
        )
        # Remove the now-empty inline app script that follows
        html = html.replace(
            '<script src="/app.js"></script>\n  <script>\n\n  </script>',
            '<script src="/app.js"></script>',
        )

        self._send_response(html, "text/html")

    def _get_generator(self) -> JSGenerator | None:
        """Get the current generator, checking hot reload manager for updates."""
        if self.hot_reload_manager:
            _, ui_spec = self.hot_reload_manager.get_specs()
            if ui_spec:
                return JSGenerator(ui_spec)
        return self.generator

    def _serve_runtime(self) -> None:
        """Serve the runtime JavaScript."""
        generator = self._get_generator()
        if not generator:
            self.send_error(500, "No UISpec loaded")
            return
        self._send_response(generator.generate_runtime(), "application/javascript")

    def _serve_app(self) -> None:
        """Serve the application JavaScript."""
        generator = self._get_generator()
        if not generator:
            self.send_error(500, "No UISpec loaded")
            return
        self._send_response(generator.generate_app_js(), "application/javascript")

    def _serve_spec(self) -> None:
        """Serve the UISpec as JSON."""
        generator = self._get_generator()
        if not generator:
            self.send_error(500, "No UISpec loaded")
            return
        self._send_response(generator.generate_spec_json(), "application/json")

    def _serve_dazzle_bar(self) -> None:
        """Serve the Dazzle Bar JavaScript bundle (v0.8.5)."""
        if not self.dev_mode:
            self.send_error(404, "Dazzle Bar not available in production mode")
            return

        try:
            from dazzle_dnr_ui.runtime.js_loader import get_dazzle_bar_js

            js_content = get_dazzle_bar_js()
            self._send_response(js_content, "application/javascript")
        except Exception as e:
            self.send_error(500, f"Failed to load Dazzle Bar: {e}")

    def _serve_css(self) -> None:
        """Serve the bundled CSS (v0.8.11)."""
        try:
            from dazzle_dnr_ui.runtime.vite_generator import _get_bundled_css

            css_content = _get_bundled_css()
            self._send_response(css_content, "text/css")
        except Exception as e:
            self.send_error(500, f"Failed to load CSS: {e}")

    def _serve_hot_reload(self) -> None:
        """Serve hot reload SSE endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        # Register with hot reload manager if available
        reload_event = None
        if self.hot_reload_manager:
            reload_event = self.hot_reload_manager.register_sse_client()

        try:
            while True:
                # Check if reload was triggered
                if reload_event and reload_event.is_set():
                    self.wfile.write(b"data: reload\n\n")
                    self.wfile.flush()
                    reload_event.clear()
                else:
                    # Send keepalive
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()

                time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            # Unregister from hot reload manager
            if self.hot_reload_manager and reload_event:
                self.hot_reload_manager.unregister_sse_client(reload_event)

    def _send_response(self, content: str, content_type: str) -> None:
        """Send HTTP response."""
        data = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        """Log HTTP requests."""
        path = args[0] if args else ""
        status = args[1] if len(args) > 1 else ""
        clean_path = path.split("?")[0]
        if self._is_api_path(clean_path) or clean_path.startswith("/dazzle/dev/"):
            print(f"[DNR API] {path} -> {status}")
        elif path != "/__hot-reload__":
            print(f"[DNR UI] {path} -> {status}")


# =============================================================================
# Combined Server
# =============================================================================


class DNRCombinedServer:
    """
    Combined development server for DNR applications.

    Runs both backend and frontend in a single process with API proxying.
    """

    def __init__(
        self,
        backend_spec: BackendSpec,
        ui_spec: UISpec,
        backend_host: str = "127.0.0.1",
        backend_port: int = 8000,
        frontend_host: str = "127.0.0.1",
        frontend_port: int = 3000,
        db_path: str | Path | None = None,
        enable_test_mode: bool = False,
        enable_auth: bool = True,  # Enable authentication by default
        enable_watch: bool = False,
        project_root: Path | None = None,
        personas: list[dict[str, Any]] | None = None,
        scenarios: list[dict[str, Any]] | None = None,
    ):
        """
        Initialize the combined server.

        Args:
            backend_spec: Backend specification
            ui_spec: UI specification
            backend_host: Backend server host
            backend_port: Backend server port
            frontend_host: Frontend server host
            frontend_port: Frontend server port
            db_path: Path to SQLite database
            enable_test_mode: Enable test endpoints (/__test__/*)
            enable_auth: Enable authentication endpoints (/auth/*)
            enable_watch: Enable hot reload file watching
            project_root: Project root directory (required for hot reload)
            personas: List of persona configurations for Dazzle Bar (v0.8.5)
            scenarios: List of scenario configurations for Dazzle Bar (v0.8.5)
        """
        self.backend_spec = backend_spec
        self.ui_spec = ui_spec
        self.backend_host = backend_host
        self.backend_port = backend_port
        self.frontend_host = frontend_host
        self.frontend_port = frontend_port
        self.db_path = Path(db_path) if db_path else Path(".dazzle/data.db")
        self.enable_test_mode = enable_test_mode
        self.enable_auth = enable_auth
        self.enable_watch = enable_watch
        self.project_root = project_root or Path.cwd()
        self.personas = personas or []
        self.scenarios = scenarios or []

        self._backend_thread: threading.Thread | None = None
        self._frontend_server: socketserver.TCPServer | None = None
        self._hot_reload_manager: HotReloadManager | None = None

    def start(self) -> None:
        """
        Start both backend and frontend servers.

        The backend runs in a background thread, frontend blocks.
        """
        # Initialize logging (JSONL format for LLM agents)
        try:
            from dazzle_dnr_back.runtime.logging import setup_logging

            log_dir = self.db_path.parent / "logs"
            setup_logging(log_dir=log_dir)
        except ImportError:
            pass  # Logging module not available

        print("\n" + "=" * 60)
        print("  DAZZLE NATIVE RUNTIME (DNR)")
        print("=" * 60)
        print()

        # Initialize hot reload if enabled
        if self.enable_watch:
            self._start_hot_reload()

        # Start backend in background thread
        self._start_backend()

        # Start frontend (blocking)
        self._start_frontend()

    def _start_hot_reload(self) -> None:
        """Initialize and start hot reload file watching."""
        from dazzle_dnr_ui.runtime.hot_reload import (
            HotReloadManager,
            create_reload_callback,
        )

        reload_callback = create_reload_callback(self.project_root)
        self._hot_reload_manager = HotReloadManager(
            project_root=self.project_root,
            on_reload=reload_callback,
        )

        # Set initial specs
        self._hot_reload_manager.set_specs(self.backend_spec, self.ui_spec)

        # Start watching
        self._hot_reload_manager.start()
        print("[DNR] Hot reload: ENABLED (watching DSL files)")

    def _start_backend(self) -> None:
        """Start the FastAPI backend in a background thread."""
        try:
            from dazzle_dnr_back.runtime.server import DNRBackendApp
        except ImportError:
            print("[DNR] Warning: dazzle_dnr_back not available, skipping backend")
            return

        # Capture flags for closure
        enable_test_mode = self.enable_test_mode
        enable_auth = self.enable_auth
        personas = self.personas
        scenarios = self.scenarios

        def run_backend() -> None:
            try:
                import uvicorn

                app_builder = DNRBackendApp(
                    self.backend_spec,
                    db_path=self.db_path,
                    use_database=True,
                    enable_test_mode=enable_test_mode,
                    enable_auth=enable_auth,
                    enable_dev_mode=True,  # Enable Dazzle Bar control plane (v0.8.5)
                    personas=personas,
                    scenarios=scenarios,
                )
                app = app_builder.build()

                config = uvicorn.Config(
                    app,
                    host=self.backend_host,
                    port=self.backend_port,
                    log_level="warning",
                )
                server = uvicorn.Server(config)
                server.run()
            except ImportError:
                print("[DNR] Warning: uvicorn not available, backend disabled")
            except OSError as e:
                if e.errno == 48 or "address already in use" in str(e).lower():
                    print(f"\n[DNR] ERROR: Backend port {self.backend_port} is already in use.")
                    print(
                        "[DNR] Stop the other process or use --api-port to specify a different port."
                    )
                    print(f"[DNR] Hint: lsof -i :{self.backend_port} | grep LISTEN")
                else:
                    print(f"[DNR] Backend error: {e}")
            except Exception as e:
                print(f"[DNR] Backend error: {e}")

        self._backend_thread = threading.Thread(target=run_backend, daemon=True)
        self._backend_thread.start()

        backend_url = f"http://{self.backend_host}:{self.backend_port}"
        docs_url = f"{backend_url}/docs"
        print(f"[DNR] Backend:  {_clickable_url(backend_url)}")
        print(f"[DNR] API Docs: {_clickable_url(docs_url)}")
        print(f"[DNR] Database: {self.db_path}")
        if self.enable_test_mode:
            print("[DNR] Test endpoints: /__test__/* (enabled)")
        if self.enable_auth:
            print("[DNR] Authentication: ENABLED (/auth/* endpoints available)")
        print()

    def _start_frontend(self) -> None:
        """Start the frontend dev server (blocking)."""
        # Configure handler
        DNRCombinedHandler.ui_spec = self.ui_spec
        DNRCombinedHandler.generator = JSGenerator(self.ui_spec)
        DNRCombinedHandler.backend_url = f"http://{self.backend_host}:{self.backend_port}"
        DNRCombinedHandler.test_mode = self.enable_test_mode
        DNRCombinedHandler.hot_reload_manager = self._hot_reload_manager

        # Build API route prefixes from backend spec entities
        api_prefixes: set[str] = set()
        for entity in self.backend_spec.entities:
            api_prefixes.add(f"/{to_api_plural(entity.name)}")
        DNRCombinedHandler.api_route_prefixes = api_prefixes

        # Create server with threading for concurrent SSE connections
        socketserver.TCPServer.allow_reuse_address = True

        # Use ThreadingTCPServer for concurrent hot reload connections
        class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            daemon_threads = True

        try:
            self._frontend_server = ThreadingTCPServer(
                (self.frontend_host, self.frontend_port),
                DNRCombinedHandler,
            )
        except OSError as e:
            if e.errno == 48 or "address already in use" in str(e).lower():
                print(f"\n[DNR] ERROR: Port {self.frontend_port} is already in use.")
                print("[DNR] Stop the other process or use --port to specify a different port.")
                print(f"[DNR] Hint: lsof -i :{self.frontend_port} | grep LISTEN")
                raise SystemExit(1)
            raise

        frontend_url = f"http://{self.frontend_host}:{self.frontend_port}"
        print(f"[DNR] Frontend: {_clickable_url(frontend_url)}")
        print()
        print("Press Ctrl+C to stop")
        print("-" * 60)
        print()

        try:
            self._frontend_server.serve_forever()
        except KeyboardInterrupt:
            print("\n[DNR] Shutting down...")
        finally:
            if self._hot_reload_manager:
                self._hot_reload_manager.stop()
            self._frontend_server.shutdown()

    def stop(self) -> None:
        """Stop both servers."""
        if self._frontend_server:
            self._frontend_server.shutdown()


# =============================================================================
# Convenience Functions
# =============================================================================


def run_combined_server(
    backend_spec: BackendSpec,
    ui_spec: UISpec,
    backend_port: int = 8000,
    frontend_port: int = 3000,
    db_path: str | Path | None = None,
    enable_test_mode: bool = False,
    enable_auth: bool = True,  # Enable authentication by default
    host: str = "127.0.0.1",
    enable_watch: bool = False,
    project_root: Path | None = None,
    personas: list[dict[str, Any]] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
) -> None:
    """
    Run a combined DNR development server.

    Args:
        backend_spec: Backend specification
        ui_spec: UI specification
        backend_port: Backend server port
        frontend_port: Frontend server port
        db_path: Path to SQLite database
        enable_test_mode: Enable test endpoints (/__test__/*)
        enable_auth: Enable authentication endpoints (/auth/*)
        host: Host to bind both servers to
        enable_watch: Enable hot reload file watching
        project_root: Project root directory (for hot reload)
        personas: List of persona configurations for Dazzle Bar (v0.8.5)
        scenarios: List of scenario configurations for Dazzle Bar (v0.8.5)
    """
    server = DNRCombinedServer(
        backend_spec=backend_spec,
        ui_spec=ui_spec,
        backend_host=host,
        backend_port=backend_port,
        frontend_host=host,
        frontend_port=frontend_port,
        db_path=db_path,
        enable_test_mode=enable_test_mode,
        enable_auth=enable_auth,
        enable_watch=enable_watch,
        project_root=project_root,
        personas=personas,
        scenarios=scenarios,
    )
    server.start()


def run_frontend_only(
    ui_spec: UISpec,
    host: str = "127.0.0.1",
    port: int = 3000,
    backend_url: str = "http://127.0.0.1:8000",
) -> None:
    """
    Run only the frontend dev server with API proxy.

    Args:
        ui_spec: UI specification
        host: Host to bind to
        port: Port to bind to
        backend_url: URL of the backend to proxy to
    """
    # Configure handler
    DNRCombinedHandler.ui_spec = ui_spec
    DNRCombinedHandler.generator = JSGenerator(ui_spec)
    DNRCombinedHandler.backend_url = backend_url

    socketserver.TCPServer.allow_reuse_address = True
    try:
        server = socketserver.TCPServer((host, port), DNRCombinedHandler)
    except OSError as e:
        if e.errno == 48 or "address already in use" in str(e).lower():
            print(f"\n[DNR-UI] ERROR: Port {port} is already in use.")
            print("[DNR-UI] Stop the other process or use --port to specify a different port.")
            print(f"[DNR-UI] Hint: lsof -i :{port} | grep LISTEN")
            raise SystemExit(1)
        raise

    frontend_url = f"http://{host}:{port}"
    print(f"[DNR-UI] Frontend server: {_clickable_url(frontend_url)}")
    print(f"[DNR-UI] Backend proxy:   {_clickable_url(backend_url)}")
    print("[DNR-UI] Press Ctrl+C to stop")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[DNR-UI] Shutting down...")
    finally:
        server.shutdown()


def run_backend_only(
    backend_spec: BackendSpec,
    host: str = "127.0.0.1",
    port: int = 8000,
    db_path: str | Path | None = None,
    enable_test_mode: bool = False,
    enable_graphql: bool = False,
) -> None:
    """
    Run only the FastAPI backend server.

    Args:
        backend_spec: Backend specification
        host: Host to bind to
        port: Port to bind to
        db_path: Path to SQLite database
        enable_test_mode: Enable test endpoints (/__test__/*)
        enable_graphql: Enable GraphQL endpoint at /graphql
    """
    try:
        import uvicorn

        from dazzle_dnr_back.runtime.server import DNRBackendApp
    except ImportError as e:
        print(f"[DNR] Error: Required dependencies not available: {e}")
        print("[DNR] Install with: pip install fastapi uvicorn dazzle-dnr-back")
        return

    print("\n" + "=" * 60)
    print("  DAZZLE NATIVE RUNTIME (DNR) - Backend Only")
    print("=" * 60)
    print()

    app_builder = DNRBackendApp(
        backend_spec,
        db_path=db_path,
        use_database=True,
        enable_test_mode=enable_test_mode,
    )
    app = app_builder.build()

    # Mount GraphQL if enabled
    if enable_graphql:
        try:
            from dazzle_dnr_back.graphql import mount_graphql

            mount_graphql(
                app,
                backend_spec,
                services=app_builder.services,
                repositories=app_builder.repositories,
            )
            graphql_url = f"http://{host}:{port}/graphql"
            print(f"[DNR] GraphQL: {_clickable_url(graphql_url)}")
        except ImportError:
            print("[DNR] Warning: GraphQL not available (install strawberry-graphql)")

    backend_url = f"http://{host}:{port}"
    docs_url = f"{backend_url}/docs"
    print(f"[DNR] Backend:  {_clickable_url(backend_url)}")
    print(f"[DNR] API Docs: {_clickable_url(docs_url)}")
    print(f"[DNR] Database: {db_path}")
    if enable_test_mode:
        print("[DNR] Test endpoints: /__test__/* (enabled)")
    print()
    print("Press Ctrl+C to stop")
    print("-" * 60)
    print()

    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        print("\n[DNR] Shutting down...")
    except OSError as e:
        if e.errno == 48 or "address already in use" in str(e).lower():
            print(f"\n[DNR] ERROR: Port {port} is already in use.")
            print("[DNR] Stop the other process or use --api-port to specify a different port.")
            print(f"[DNR] Hint: lsof -i :{port} | grep LISTEN")
        else:
            raise
