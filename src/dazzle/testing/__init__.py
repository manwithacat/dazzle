"""
DAZZLE Semantic E2E Testing Package.

This package provides tools for generating and running semantic E2E tests
from AppSpec definitions.
"""

from dazzle.testing.playwright_codegen import (
    generate_test_file,
    generate_test_module,
    generate_tests_for_app,
)
from dazzle.testing.testspec_generator import generate_e2e_testspec

__all__ = [
    "generate_e2e_testspec",
    "generate_test_module",
    "generate_test_file",
    "generate_tests_for_app",
]
