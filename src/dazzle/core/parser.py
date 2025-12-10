from pathlib import Path

from . import ir
from .dsl_parser_impl import parse_dsl
from .expander import VocabExpander
from .vocab import load_manifest


def parse_modules(files: list[Path]) -> list[ir.ModuleIR]:
    """
    Parse DSL files into ModuleIR structures.

    Uses the full DSL parser to extract:
    - Module name and use declarations
    - App name and title
    - All DSL constructs (entities, surfaces, experiences, etc.)

    If a vocabulary manifest exists, expands @use directives before parsing.

    Args:
        files: List of .dsl file paths to parse

    Returns:
        List of ModuleIR objects with complete parsed IR fragments
    """
    modules: list[ir.ModuleIR] = []

    # Try to load vocabulary manifest (optional)
    expander = _load_vocabulary_expander(files)

    for f in files:
        text = f.read_text(encoding="utf-8")

        # Expand vocabulary references if manifest exists
        if expander:
            try:
                text = expander.expand_text(text)
            except Exception as e:
                # If expansion fails, include file context in error
                from .errors import DazzleError

                raise DazzleError(f"Vocabulary expansion failed in {f}: {e}")

        # Parse DSL file
        module_name, app_name, app_title, uses, fragment = parse_dsl(text, f)

        # Use filename as fallback module name
        if module_name is None:
            module_name = f.stem

        modules.append(
            ir.ModuleIR(
                name=module_name,
                file=f,
                app_name=app_name,
                app_title=app_title,
                uses=uses,
                fragment=fragment,
            )
        )

    return modules


def _load_vocabulary_expander(files: list[Path]) -> VocabExpander | None:
    """
    Try to load vocabulary manifest and create expander.

    Looks for dazzle/local_vocab/manifest.yml relative to the first DSL file.
    Returns None if no manifest exists (vocabulary is optional).

    Args:
        files: List of DSL files being parsed

    Returns:
        VocabExpander if manifest exists, None otherwise
    """
    if not files:
        return None

    # Look for manifest relative to first DSL file
    # Assume project structure: project_root/dsl/*.dsl and project_root/dazzle/local_vocab/manifest.yml
    first_file = files[0]
    project_root = (
        first_file.parent.parent if first_file.parent.name == "dsl" else first_file.parent
    )
    manifest_path = project_root / "dazzle" / "local_vocab" / "manifest.yml"

    if not manifest_path.exists():
        return None

    try:
        manifest = load_manifest(manifest_path)
        return VocabExpander(manifest)
    except Exception:
        # If manifest exists but is invalid, fail silently for now
        # In a future version, we might want to emit a warning
        return None
