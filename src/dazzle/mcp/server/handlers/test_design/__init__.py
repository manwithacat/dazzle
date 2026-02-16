"""Test design tool handlers.

Handles persona test proposal, gap analysis, coverage actions,
runtime coverage, and test design persistence.
"""

from .coverage import (
    get_coverage_actions_handler,
    get_runtime_coverage_gaps_handler,
    save_runtime_coverage_handler,
)
from .gaps import get_test_gaps_handler
from .persistence import get_test_designs_handler, save_test_designs_handler
from .proposals import (
    _parse_test_design_action,
    _parse_test_design_trigger,
    propose_persona_tests_handler,
)

__all__ = [
    "_parse_test_design_action",
    "_parse_test_design_trigger",
    "get_coverage_actions_handler",
    "get_runtime_coverage_gaps_handler",
    "get_test_designs_handler",
    "get_test_gaps_handler",
    "propose_persona_tests_handler",
    "save_runtime_coverage_handler",
    "save_test_designs_handler",
]
