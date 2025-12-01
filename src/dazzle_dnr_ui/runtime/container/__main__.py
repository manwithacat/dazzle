#!/usr/bin/env python3
"""
DNR Docker Container Entrypoint.

This is the main entry point for the DNR container runtime.
It loads configuration from environment variables, reads the specs,
and starts the FastAPI server.

Usage:
    python -m dazzle_dnr_ui.runtime.container
"""

from __future__ import annotations

from pathlib import Path

import uvicorn

from .config import ContainerConfig
from .server import create_app, load_specs


def main() -> None:
    """Main entry point for the container."""
    # Load configuration from environment
    config = ContainerConfig.from_env()

    print(f"[DNR] Starting server on {config.host}:{config.api_port}")
    print(f"[DNR] Test mode: {config.test_mode}")
    print(f"[DNR] Auth enabled: {config.auth_enabled}")

    # Load specs
    backend_spec, ui_spec = load_specs(
        config.backend_spec_path,
        config.ui_spec_path,
    )

    print(f"[DNR] Entities: {[e['name'] for e in backend_spec.get('entities', [])]}")

    # Create app
    static_dir = Path("/app/static")
    app = create_app(
        backend_spec=backend_spec,
        ui_spec=ui_spec,
        test_mode=config.test_mode,
        auth_enabled=config.auth_enabled,
        static_dir=static_dir if static_dir.exists() else None,
    )

    # Run server
    uvicorn.run(app, host=config.host, port=config.api_port)


if __name__ == "__main__":
    main()
