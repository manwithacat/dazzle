"""
Development server for DNR-UI.

Serves the generated UI with hot reload support.
"""

from __future__ import annotations

import http.server
import json
import socketserver
from pathlib import Path
from typing import Any

from dazzle_dnr_ui.runtime.js_generator import JSGenerator
from dazzle_dnr_ui.specs import UISpec

# =============================================================================
# Request Handler
# =============================================================================


class DNRDevHandler(http.server.SimpleHTTPRequestHandler):
    """
    HTTP request handler for DNR-UI development.

    Serves generated UI and provides hot reload support.
    """

    spec: UISpec | None = None
    generator: JSGenerator | None = None

    def do_GET(self) -> None:
        """Handle GET requests."""
        path = self.path.split("?")[0]  # Remove query string

        if path == "/dnr-runtime.js":
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
        print(f"[DNR-UI] {args[0]} {args[1]} {args[2]}")


# =============================================================================
# Dev Server
# =============================================================================


class DNRDevServer:
    """
    Development server for DNR-UI.

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
        self.generator = JSGenerator(spec)
        self._server: socketserver.TCPServer | None = None

    def start(self) -> None:
        """
        Start the development server.

        Blocks until server is stopped.
        """
        # Configure handler
        DNRDevHandler.spec = self.spec
        DNRDevHandler.generator = self.generator

        # Create server
        socketserver.TCPServer.allow_reuse_address = True
        self._server = socketserver.TCPServer((self.host, self.port), DNRDevHandler)

        print("[DNR-UI] Development server starting...")
        print(f"[DNR-UI] Serving: {self.spec.name}")
        print(f"[DNR-UI] URL: http://{self.host}:{self.port}")
        print("[DNR-UI] Press Ctrl+C to stop")
        print()

        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            print("\n[DNR-UI] Shutting down...")
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
        self.generator = JSGenerator(spec)
        DNRDevHandler.spec = spec
        DNRDevHandler.generator = self.generator


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
    server = DNRDevServer(spec, host, port)
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
