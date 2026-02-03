"""
Docker runner for Dazzle applications.

Contains the DockerRunner class and DockerRunConfig for running
Dazzle applications in Docker containers.

Uses a single-container architecture: the Python backend serves both
the API and the Jinja2/HTMX frontend via bundled CSS.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .templates import (
    DAZZLE_BACKEND_DOCKERFILE,
    DAZZLE_SINGLE_COMPOSE_TEMPLATE,
)
from .utils import is_docker_available


def _get_container_package_path() -> Path:
    """Get the path to the container runtime package."""
    # The container package is at dazzle_ui/runtime/container/
    return Path(__file__).parent.parent / "container"


def _copy_container_package(dest_dir: Path) -> None:
    """
    Copy the container runtime package to the Docker build context.

    Args:
        dest_dir: Destination directory for the build context
    """
    container_src = _get_container_package_path()
    container_dest = dest_dir / "container"

    if container_dest.exists():
        shutil.rmtree(container_dest)

    # Copy all Python files from the container package
    container_dest.mkdir(exist_ok=True)
    for py_file in container_src.glob("*.py"):
        shutil.copy2(py_file, container_dest / py_file.name)


def _copy_css_files(dest_dir: Path) -> None:
    """
    Copy CSS files to the Docker build context for static serving.

    Args:
        dest_dir: Destination directory for the build context
    """
    from dazzle_ui.runtime.css_loader import get_bundled_css

    styles_dir = dest_dir / "static" / "styles"
    styles_dir.mkdir(parents=True, exist_ok=True)

    # Write bundled CSS
    css_content = get_bundled_css()
    (styles_dir / "dazzle.css").write_text(css_content)


@dataclass
class DockerRunConfig:
    """Configuration for running Dazzle in Docker."""

    project_path: Path
    frontend_port: int = 3000
    api_port: int = 8000
    container_name: str | None = None
    project_name: str | None = None
    image_name: str = "dazzle-app"
    test_mode: bool = False
    dev_mode: bool = True
    auth_enabled: bool = True
    rebuild: bool = False
    detach: bool = False


class DockerRunner:
    """
    Runs Dazzle applications in Docker containers.

    Uses a single-container architecture where the Python backend
    serves both the API and the Jinja2/HTMX frontend.
    """

    def __init__(self, config: DockerRunConfig):
        """
        Initialize the Docker runner.

        Args:
            config: Docker run configuration
        """
        self.config = config
        self.project_path = config.project_path.resolve()

        self.project_name = config.project_name or self.project_path.name

        if config.container_name:
            self.container_name = config.container_name
        else:
            self.container_name = f"dazzle-{self.project_name}"

        self.image_name = f"{config.image_name}:{self.project_name}"

    def run(self) -> int:
        """
        Run the Dazzle application in a Docker container.

        Returns:
            Exit code from Docker run
        """
        print("\n" + "=" * 60)
        print("  DAZZLE - Docker Mode")
        print("=" * 60)
        print()

        if not is_docker_available():
            print("[Dazzle] ERROR: Docker is not available")
            print("[Dazzle] Please install Docker or use --local flag")
            return 1

        return self._run_container()

    def _generate_specs(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Generate backend spec and UI spec from DSL files.

        Returns:
            Tuple of (backend_spec_dict, ui_spec_dict)
        """
        from dazzle.core.fileset import discover_dsl_files
        from dazzle.core.linker import build_appspec
        from dazzle.core.manifest import load_manifest
        from dazzle.core.parser import parse_modules
        from dazzle_back.converters import convert_appspec_to_backend
        from dazzle_ui.converters import convert_appspec_to_ui

        manifest_path = self.project_path / "dazzle.toml"
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(self.project_path, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        backend_spec = convert_appspec_to_backend(appspec)
        ui_spec = convert_appspec_to_ui(appspec, shell_config=mf.shell)

        return (
            backend_spec.model_dump(by_alias=True),
            ui_spec.model_dump(by_alias=True),
        )

    def _run_container(self) -> int:
        """
        Run a single container with API + Jinja2/HTMX frontend.

        Returns:
            Exit code from docker compose
        """
        import json

        print("[Dazzle] Setting up container...")
        print()

        print("[Dazzle] Generating specs from DSL...")
        try:
            backend_spec, ui_spec_dict = self._generate_specs()
        except Exception as e:
            print(f"[Dazzle] ERROR: Failed to generate specs: {e}")
            return 1

        # Create persistent build directory in project
        build_dir = self.project_path / ".dazzle" / "docker"
        if self.config.rebuild and build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True, exist_ok=True)

        # Backend context (single container)
        backend_dir = build_dir / "backend"
        backend_dir.mkdir(exist_ok=True)

        backend_dockerfile = DAZZLE_BACKEND_DOCKERFILE.format(
            api_port=self.config.api_port,
        )
        (backend_dir / "Dockerfile").write_text(backend_dockerfile)
        (backend_dir / "backend_spec.json").write_text(json.dumps(backend_spec, indent=2))
        (backend_dir / "ui_spec.json").write_text(json.dumps(ui_spec_dict, indent=2))

        # Copy container runtime package
        _copy_container_package(backend_dir)

        # Copy bundled CSS for static serving
        _copy_css_files(backend_dir)

        # Generate docker-compose.yaml (single container)
        volume_name = f"{self.container_name}-data".replace("-", "_")
        compose_content = DAZZLE_SINGLE_COMPOSE_TEMPLATE.format(
            project_name=self.project_name,
            container_name=self.container_name,
            api_port=self.config.api_port,
            frontend_port=self.config.frontend_port,
            test_mode="1" if self.config.test_mode else "0",
            dev_mode="1" if self.config.dev_mode else "0",
            auth_enabled="1" if self.config.auth_enabled else "0",
            volume_name=volume_name,
        )
        compose_file = build_dir / "docker-compose.yaml"
        compose_file.write_text(compose_content)

        # Stop existing containers
        print("[Dazzle] Stopping any existing containers...")
        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "down"],
            capture_output=True,
        )

        # Build and run
        print("[Dazzle] Building container...")
        build_result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "build"],
            cwd=str(build_dir),
        )
        if build_result.returncode != 0:
            print("[Dazzle] ERROR: Docker compose build failed")
            return 1

        print()
        print(f"[Dazzle] App:      http://localhost:{self.config.frontend_port}")
        print(f"[Dazzle] API Docs: http://localhost:{self.config.api_port}/docs")
        print()

        if self.config.detach:
            print("[Dazzle] Running in background...")
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "up", "-d"],
                cwd=str(build_dir),
            )
            if result.returncode == 0:
                print(f"[Dazzle] Container started: {self.container_name}")
                print(f"[Dazzle] Stop with: docker compose -f {compose_file} down")
            return result.returncode
        else:
            print("Press Ctrl+C to stop")
            print("-" * 60)
            print()

            try:
                result = subprocess.run(
                    ["docker", "compose", "-f", str(compose_file), "up"],
                    cwd=str(build_dir),
                )
                return result.returncode
            except KeyboardInterrupt:
                print("\n[Dazzle] Shutting down...")
                subprocess.run(
                    ["docker", "compose", "-f", str(compose_file), "down"],
                    cwd=str(build_dir),
                )
                return 0


# =============================================================================
# Convenience Functions
# =============================================================================


def run_in_docker(
    project_path: Path | str,
    frontend_port: int = 3000,
    api_port: int = 8000,
    test_mode: bool = False,
    dev_mode: bool = True,
    auth_enabled: bool = True,
    rebuild: bool = False,
    detach: bool = False,
    project_name: str | None = None,
) -> int:
    """
    Run a Dazzle application in Docker.

    Args:
        project_path: Path to the Dazzle project
        frontend_port: Frontend server port
        api_port: Backend API port
        test_mode: Enable test endpoints
        dev_mode: Enable Dazzle Bar
        auth_enabled: Enable authentication endpoints
        rebuild: Force rebuild of Docker image
        detach: Run in background
        project_name: Project name from manifest

    Returns:
        Exit code
    """
    config = DockerRunConfig(
        project_path=Path(project_path),
        frontend_port=frontend_port,
        api_port=api_port,
        test_mode=test_mode,
        dev_mode=dev_mode,
        auth_enabled=auth_enabled,
        rebuild=rebuild,
        detach=detach,
        project_name=project_name,
    )
    runner = DockerRunner(config)
    return runner.run()


def stop_docker_container(
    project_path: Path | str,
    project_name: str | None = None,
) -> bool:
    """
    Stop a running Dazzle Docker container.

    Args:
        project_path: Path to the Dazzle project
        project_name: Project name from manifest

    Returns:
        True if container was stopped
    """
    base_name = project_name or Path(project_path).resolve().name
    container_name = f"dazzle-{base_name}"
    try:
        result = subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
