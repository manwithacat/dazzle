"""Core DAZZLE: IR, parser, linker, validator, project init."""

from . import ir
from .errors import (
    BackendError,
    DazzleError,
    ErrorContext,
    LinkError,
    ParseError,
    ValidationError,
)
from .init_impl import InitError, init_project, list_examples
from .linker import build_appspec
from .lint import lint_appspec
from .parser import parse_modules
from .project import load_project, load_project_with_manifest

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
    "load_project",
    "load_project_with_manifest",
    "init_project",
    "list_examples",
    "InitError",
]
