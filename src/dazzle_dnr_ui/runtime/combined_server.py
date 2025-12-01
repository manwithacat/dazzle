"""
Combined DNR Server - runs both backend and frontend.

Provides a unified development server that:
1. Runs FastAPI backend on port 8000
2. Runs UI dev server on port 3000 with API proxy
3. Handles hot reload for both
"""

from __future__ import annotations

import http.server
import socketserver
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle_dnr_ui.runtime.js_generator import JSGenerator
from dazzle_dnr_ui.specs import UISpec

if TYPE_CHECKING:
    from dazzle_dnr_back.specs import BackendSpec


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

    def do_GET(self) -> None:
        """Handle GET requests."""
        path = self.path.split("?")[0]

        # Proxy API requests to backend
        if path.startswith("/api/"):
            self._proxy_request("GET")
        elif path.startswith("/__test__/"):
            self._proxy_request("GET")
        elif path == "/dnr-runtime.js":
            self._serve_runtime()
        elif path == "/app.js":
            self._serve_app()
        elif path == "/ui-spec.json":
            self._serve_spec()
        elif path == "/__hot-reload__":
            self._serve_hot_reload()
        elif path == "/health":
            self._proxy_request("GET")
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
        if self.path.startswith("/api/"):
            self._proxy_request("POST")
        elif self.path.startswith("/__test__/"):
            self._proxy_request("POST")
        else:
            self.send_error(405, "Method Not Allowed")

    def do_PUT(self) -> None:
        """Handle PUT requests."""
        if self.path.startswith("/api/"):
            self._proxy_request("PUT")
        else:
            self.send_error(405, "Method Not Allowed")

    def do_DELETE(self) -> None:
        """Handle DELETE requests."""
        if self.path.startswith("/api/"):
            self._proxy_request("DELETE")
        elif self.path.startswith("/__test__/"):
            self._proxy_request("DELETE")
        else:
            self.send_error(405, "Method Not Allowed")

    def do_PATCH(self) -> None:
        """Handle PATCH requests."""
        if self.path.startswith("/api/"):
            self._proxy_request("PATCH")
        else:
            self.send_error(405, "Method Not Allowed")

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

    def _serve_runtime(self) -> None:
        """Serve the runtime JavaScript."""
        if not self.generator:
            self.send_error(500, "No UISpec loaded")
            return
        self._send_response(self.generator.generate_runtime(), "application/javascript")

    def _serve_app(self) -> None:
        """Serve the application JavaScript."""
        if not self.generator:
            self.send_error(500, "No UISpec loaded")
            return
        self._send_response(self.generator.generate_app_js(), "application/javascript")

    def _serve_spec(self) -> None:
        """Serve the UISpec as JSON."""
        if not self.generator:
            self.send_error(500, "No UISpec loaded")
            return
        self._send_response(self.generator.generate_spec_json(), "application/json")

    def _serve_hot_reload(self) -> None:
        """Serve hot reload SSE endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            while True:
                import time

                time.sleep(1)
                self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

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
        if path.startswith("/api/"):
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
        enable_auth: bool = False,
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

        self._backend_thread: threading.Thread | None = None
        self._frontend_server: socketserver.TCPServer | None = None

    def start(self) -> None:
        """
        Start both backend and frontend servers.

        The backend runs in a background thread, frontend blocks.
        """
        print("\n" + "=" * 60)
        print("  DAZZLE NATIVE RUNTIME (DNR)")
        print("=" * 60)
        print()

        # Start backend in background thread
        self._start_backend()

        # Start frontend (blocking)
        self._start_frontend()

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

        def run_backend() -> None:
            try:
                import uvicorn

                app_builder = DNRBackendApp(
                    self.backend_spec,
                    db_path=self.db_path,
                    use_database=True,
                    enable_test_mode=enable_test_mode,
                    enable_auth=enable_auth,
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
            except Exception as e:
                print(f"[DNR] Backend error: {e}")

        self._backend_thread = threading.Thread(target=run_backend, daemon=True)
        self._backend_thread.start()

        print(f"[DNR] Backend:  http://{self.backend_host}:{self.backend_port}")
        print(f"[DNR] API Docs: http://{self.backend_host}:{self.backend_port}/docs")
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

        # Create server
        socketserver.TCPServer.allow_reuse_address = True
        self._frontend_server = socketserver.TCPServer(
            (self.frontend_host, self.frontend_port),
            DNRCombinedHandler,
        )

        print(f"[DNR] Frontend: http://{self.frontend_host}:{self.frontend_port}")
        print()
        print("Press Ctrl+C to stop")
        print("-" * 60)
        print()

        try:
            self._frontend_server.serve_forever()
        except KeyboardInterrupt:
            print("\n[DNR] Shutting down...")
        finally:
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
    enable_auth: bool = False,
    host: str = "127.0.0.1",
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
    server = socketserver.TCPServer((host, port), DNRCombinedHandler)

    print(f"[DNR-UI] Frontend server: http://{host}:{port}")
    print(f"[DNR-UI] Backend proxy:   {backend_url}")
    print("[DNR-UI] Press Ctrl+C to stop")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[DNR-UI] Shutting down...")
    finally:
        server.shutdown()


def run_backend_only(
    backend_spec: "BackendSpec",
    host: str = "127.0.0.1",
    port: int = 8000,
    db_path: str | Path | None = None,
    enable_test_mode: bool = False,
) -> None:
    """
    Run only the FastAPI backend server.

    Args:
        backend_spec: Backend specification
        host: Host to bind to
        port: Port to bind to
        db_path: Path to SQLite database
        enable_test_mode: Enable test endpoints (/__test__/*)
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

    print(f"[DNR] Backend:  http://{host}:{port}")
    print(f"[DNR] API Docs: http://{host}:{port}/docs")
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
