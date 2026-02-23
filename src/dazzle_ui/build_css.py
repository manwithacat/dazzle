"""CSS build system for Dazzle UI.

Downloads the Tailwind CSS standalone CLI on first use and compiles a
production CSS bundle from the template directory. The bundle contains
only the utility classes actually used in templates — no runtime JIT.

Usage::

    from dazzle_ui.build_css import build_css
    build_css(output_path=Path("static/css/dazzle-bundle.css"))

Or via CLI::

    dazzle build-css
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Tailwind CSS standalone CLI with DaisyUI (via dobicinaitis/tailwind-cli-extra)
_TAILWIND_EXTRA_VERSION = "2.8.1"
_TAILWIND_BASE_URL = f"https://github.com/dobicinaitis/tailwind-cli-extra/releases/download/v{_TAILWIND_EXTRA_VERSION}"

# Binary names by platform (no version suffix in filenames)
_PLATFORM_BINARIES: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "tailwindcss-extra-macos-arm64",
    ("darwin", "x86_64"): "tailwindcss-extra-macos-x64",
    ("linux", "x86_64"): "tailwindcss-extra-linux-x64",
    ("linux", "aarch64"): "tailwindcss-extra-linux-arm64",
}


def _cache_dir() -> Path:
    """Return the Dazzle cache directory for CLI binaries."""
    cache = Path(os.environ.get("DAZZLE_CACHE_DIR", Path.home() / ".dazzle" / "cache"))
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _get_platform_key() -> tuple[str, str]:
    """Get the (system, machine) key for the current platform."""
    system = platform.system().lower()
    machine = platform.machine()
    # Normalize arm64 variants
    if machine == "arm64":
        machine = "arm64"
    elif machine == "AMD64":
        machine = "x86_64"
    return (system, machine)


def get_tailwind_binary() -> Path | None:
    """Get the path to the Tailwind CSS CLI binary, downloading if needed.

    Returns:
        Path to the binary, or None if the platform is unsupported.
    """
    # Check if tailwindcss is already on PATH
    system_tw = shutil.which("tailwindcss")
    if system_tw:
        return Path(system_tw)

    key = _get_platform_key()
    binary_name = _PLATFORM_BINARIES.get(key)
    if binary_name is None:
        logger.warning(
            "Tailwind CSS standalone CLI not available for %s/%s. "
            "Install tailwindcss manually or use `npm install tailwindcss`.",
            key[0],
            key[1],
        )
        return None

    cached = _cache_dir() / "tailwindcss"
    version_file = _cache_dir() / "tailwindcss.version"

    # Check if cached version matches
    if cached.exists() and version_file.exists():
        cached_version = version_file.read_text().strip()
        if cached_version == _TAILWIND_EXTRA_VERSION:
            return cached

    # Download
    url = f"{_TAILWIND_BASE_URL}/{binary_name}"
    logger.info("Downloading Tailwind CSS CLI v%s for %s/%s...", _TAILWIND_EXTRA_VERSION, *key)

    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=60) as resp:
            data = resp.read()

        cached.write_bytes(data)
        cached.chmod(cached.stat().st_mode | stat.S_IEXEC)
        version_file.write_text(_TAILWIND_EXTRA_VERSION)
        logger.info("Tailwind CSS CLI cached at %s", cached)
        return cached

    except Exception as e:
        logger.error("Failed to download Tailwind CSS CLI: %s", e)
        return None


def _template_dir() -> Path:
    """Get the Dazzle UI templates directory."""
    return Path(__file__).parent / "templates"


def _static_dir() -> Path:
    """Get the Dazzle UI static directory."""
    return Path(__file__).parent / "runtime" / "static"


def _create_input_css(tmp_dir: Path) -> Path:
    """Create the Tailwind input CSS file with @import directives."""
    input_css = tmp_dir / "input.css"
    input_css.write_text(
        """\
@import "tailwindcss";
@plugin "daisyui";
"""
    )
    return input_css


def build_css(
    *,
    output_path: Path | None = None,
    project_root: Path | None = None,
    minify: bool = True,
) -> Path | None:
    """Build the compiled Tailwind CSS bundle.

    Scans all Dazzle UI templates (and optionally project templates) for
    Tailwind utility classes and produces a single CSS file.

    Args:
        output_path: Where to write the bundle. Defaults to
            ``src/dazzle_ui/runtime/static/css/dazzle-bundle.css``.
        project_root: Optional project root for scanning project templates.
        minify: Whether to minify the output.

    Returns:
        Path to the generated CSS file, or None on failure.
    """
    tw_bin = get_tailwind_binary()
    if tw_bin is None:
        logger.error(
            "Cannot build CSS: Tailwind CSS CLI not available. "
            "Install it with: npm install -g tailwindcss"
        )
        return None

    if output_path is None:
        output_path = _static_dir() / "css" / "dazzle-bundle.css"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Collect content paths to scan
    content_paths = [str(_template_dir() / "**" / "*.html")]
    # Also scan the static JS for any class references
    content_paths.append(str(_static_dir() / "js" / "*.js"))

    if project_root:
        # Scan project templates and overrides
        proj_templates = project_root / "templates"
        if proj_templates.is_dir():
            content_paths.append(str(proj_templates / "**" / "*.html"))
        proj_static = project_root / "static"
        if proj_static.is_dir():
            content_paths.append(str(proj_static / "**" / "*.{html,js}"))

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        input_css = _create_input_css(tmp_dir)

        cmd = [
            str(tw_bin),
            "--input",
            str(input_css),
            "--output",
            str(output_path),
            "--content",
            ",".join(content_paths),
        ]

        if minify:
            cmd.append("--minify")

        logger.info("Building CSS: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(_template_dir().parent),
            )

            if result.returncode != 0:
                logger.error("Tailwind CSS build failed:\n%s", result.stderr)
                return None

            size_kb = output_path.stat().st_size / 1024
            logger.info("CSS bundle built: %s (%.1f KB)", output_path, size_kb)
            return output_path

        except subprocess.TimeoutExpired:
            logger.error("Tailwind CSS build timed out")
            return None
        except FileNotFoundError:
            logger.error("Tailwind CSS CLI not found at %s", tw_bin)
            return None
