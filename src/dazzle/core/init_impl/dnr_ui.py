"""
DNR UI generation from DSL.

Generates DNR UI artifacts from the project's DSL files.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def generate_dnr_ui(
    project_dir: Path,
    log: "Callable[[str], None] | None" = None,
) -> bool:
    """
    Generate DNR UI artifacts from the project's DSL.

    This ensures that dnr-ui/ is always generated from the canonical
    vite_generator templates, not copied from stale example files.

    Args:
        project_dir: Project directory containing dazzle.toml and dsl/
        log: Optional logging callback

    Returns:
        True if generation succeeded, False otherwise
    """
    if log is None:
        log = lambda msg: None  # noqa: E731

    # Check if dazzle.toml exists
    manifest_path = project_dir / "dazzle.toml"
    if not manifest_path.exists():
        log("  Skipping dnr-ui generation (no dazzle.toml)")
        return False

    try:
        # Import required modules
        from dazzle.core.dsl_parser import parse_dsl
        from dazzle.core.ir import ModuleIR
        from dazzle.core.linker import build_appspec
        from dazzle.core.manifest import load_manifest

        # Try to import DNR UI - it's optional
        try:
            from dazzle_dnr_ui.converters import convert_appspec_to_ui
            from dazzle_dnr_ui.runtime import generate_vite_app
        except ImportError:
            log("  Skipping dnr-ui generation (dazzle-dnr-ui not installed)")
            return False

        # Load manifest (validates it exists and is well-formed)
        _manifest = load_manifest(manifest_path)

        # Discover and parse DSL files
        dsl_dir = project_dir / "dsl"
        if not dsl_dir.exists():
            log("  Skipping dnr-ui generation (no dsl/ directory)")
            return False

        dsl_files = list(dsl_dir.glob("**/*.dsl"))
        if not dsl_files:
            log("  Skipping dnr-ui generation (no .dsl files found)")
            return False

        # Parse all DSL files
        modules: list[ModuleIR] = []
        for dsl_file in dsl_files:
            content = dsl_file.read_text()
            module_name, app_name, app_title, uses, fragment = parse_dsl(content, dsl_file)

            if module_name is None:
                log(f"  Skipping {dsl_file} (no module name found)")
                continue

            module_ir = ModuleIR(
                name=module_name,
                file=dsl_file,
                app_name=app_name,
                app_title=app_title,
                uses=uses,
                fragment=fragment,
            )
            modules.append(module_ir)

        if not modules:
            log("  Skipping dnr-ui generation (no modules parsed)")
            return False

        # Build AppSpec
        root_module = modules[0].name
        appspec = build_appspec(modules, root_module)

        # Convert to UISpec
        ui_spec = convert_appspec_to_ui(appspec)

        # Generate Vite project
        output_dir = project_dir / "dnr-ui"
        output_dir.mkdir(parents=True, exist_ok=True)

        files = generate_vite_app(ui_spec, str(output_dir))
        log(f"  Generated dnr-ui/ ({len(files)} files)")

        return True

    except Exception as e:
        # Don't fail init if dnr-ui generation fails
        log(f"  Warning: dnr-ui generation failed ({e})")
        return False
