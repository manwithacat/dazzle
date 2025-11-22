"""Core DAZZLE functionality: IR, parser, linker, validator, project initialization, incremental builds, stacks."""

from . import ir
from .errors import (
    DazzleError,
    ParseError,
    LinkError,
    ValidationError,
    BackendError,
    ErrorContext,
)
from .parser import parse_modules
from .linker import build_appspec
from .lint import lint_appspec
from .init import init_project, list_examples, InitError
from .state import (
    BuildState,
    StateError,
    load_state,
    save_state,
    clear_state,
    compute_dsl_hashes,
)
from .changes import ChangeSet, detect_changes
from .stacks import (
    StackError,
    StackPreset,
    get_stack_preset,
    list_stack_presets,
    resolve_stack_backends,
    validate_stack_backends,
    get_stack_description,
)

__all__ = [
    "ir",
    "DazzleError",
    "ParseError",
    "LinkError",
    "ValidationError",
    "BackendError",
    "ErrorContext",
    "parse_modules",
    "build_appspec",
    "lint_appspec",
    "init_project",
    "list_examples",
    "InitError",
    "BuildState",
    "StateError",
    "load_state",
    "save_state",
    "clear_state",
    "compute_dsl_hashes",
    "ChangeSet",
    "detect_changes",
    "StackError",
    "StackPreset",
    "get_stack_preset",
    "list_stack_presets",
    "resolve_stack_backends",
    "validate_stack_backends",
    "get_stack_description",
]
