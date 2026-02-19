"""
Development server for Dazzle UI.

Serves the generated UI with hot reload support.
"""

from __future__ import annotations

import http.server
import json
import socketserver
from pathlib import Path
from typing import Any

from dazzle_ui.specs import UISpec

# JSGenerator was removed in the HTMX migration.
# Dev server now uses template rendering.

# =============================================================================
# Request Handler
# =============================================================================


class DazzleDevHandler(http.server.SimpleHTTPRequestHandler):
    """
    HTTP request handler for Dazzle UI development.

    Serves generated UI and provides hot reload support.
    """

    spec: UISpec | None = None
    generator: Any = None

    def do_GET(self) -> None:
        """Handle GET requests."""
        path = self.path.split("?")[0]  # Remove query string

        if path == "/dazzle-runtime.js":
            self._serve_runtime()
        elif path == "/app.js":
            self._serve_app()
        elif path == "/ui-spec.json":
            self._serve_spec()
        elif path == "/__hot-reload__":
            self._serve_hot_reload()
        elif path.startswith(("/auth/", "/files/", "/pages/")):
            # API routes should 404 (they go to backend server)
            self.send_error(404, "API route - use backend server")
        else:
            # For SPA: serve HTML for all non-static routes
            # This enables path-based routing (e.g., /task/create, /task/123)
            self._serve_html()

    def _serve_html(self) -> None:
        """Serve the main HTML page."""
        if not self.generator:
            self.send_error(500, "No UISpec loaded")
            return

        html = self.generator.generate_html(include_runtime=False)
        # Inject hot reload script
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
            '<script src="/dazzle-runtime.js"></script>\n  <script src="/app.js"></script>\n  <script>',
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

        # Keep connection open
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
        print(f"[Dazzle] {args[0]} {args[1]} {args[2]}")


# =============================================================================
# Dev Server
# =============================================================================


class DazzleDevServer:
    """
    Development server for Dazzle UI.

    Provides:
    - Hot reload on spec changes
    - Generated file serving
    - API proxy (optional)
    """

    def __init__(
        self,
        spec: UISpec,
        host: str = "127.0.0.1",
        port: int = 3000,
    ):
        """
        Initialize the dev server.

        Args:
            spec: UI specification
            host: Host to bind to
            port: Port to bind to
        """
        self.spec = spec
        self.host = host
        self.port = port
        self._server: socketserver.TCPServer | None = None

    def start(self) -> None:
        """
        Start the development server.

        Blocks until server is stopped.
        """
        # Configure handler
        DazzleDevHandler.spec = self.spec

        # Create server
        socketserver.TCPServer.allow_reuse_address = True
        self._server = socketserver.TCPServer((self.host, self.port), DazzleDevHandler)

        print("[Dazzle] Development server starting...")
        print(f"[Dazzle] Serving: {self.spec.name}")
        print(f"[Dazzle] URL: http://{self.host}:{self.port}")
        print("[Dazzle] Press Ctrl+C to stop")
        print()

        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            print("\n[Dazzle] Shutting down...")
        finally:
            self._server.shutdown()

    def stop(self) -> None:
        """Stop the server."""
        if self._server:
            self._server.shutdown()

    def update_spec(self, spec: UISpec) -> None:
        """
        Update the UISpec (for hot reload).

        Args:
            spec: New UI specification
        """
        self.spec = spec
        DazzleDevHandler.spec = spec


# =============================================================================
# Convenience Functions
# =============================================================================


def run_dev_server(
    spec: UISpec,
    host: str = "127.0.0.1",
    port: int = 3000,
) -> None:
    """
    Run a development server for UISpec.

    Args:
        spec: UI specification
        host: Host to bind to
        port: Port to bind to
    """
    server = DazzleDevServer(spec, host, port)
    server.start()


def run_dev_server_from_dict(
    spec_dict: dict[str, Any],
    host: str = "127.0.0.1",
    port: int = 3000,
) -> None:
    """
    Run a development server from a dictionary spec.

    Args:
        spec_dict: Dictionary representation of UISpec
        host: Host to bind to
        port: Port to bind to
    """
    spec = UISpec.model_validate(spec_dict)
    run_dev_server(spec, host, port)


def run_dev_server_from_json(
    json_path: str,
    host: str = "127.0.0.1",
    port: int = 3000,
) -> None:
    """
    Run a development server from a JSON file.

    Args:
        json_path: Path to JSON file containing UISpec
        host: Host to bind to
        port: Port to bind to
    """
    spec_dict = json.loads(Path(json_path).read_text())
    run_dev_server_from_dict(spec_dict, host, port)


# =============================================================================
