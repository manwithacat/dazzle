"""
DAZZLE Testing Framework

Provides comprehensive testing infrastructure for DAZZLE applications:

1. DSL-Driven Test Generation
   - Generates tests directly from AppSpec
   - Tracks coverage across entities, state machines, events, processes
   - Detects DSL changes via hash comparison

2. CRUD/State Machine Testing
   - Tests entity CRUD operations
   - Tests state machine transitions
   - Validates required fields and constraints

3. Event Flow Testing
   - Simulates Kafka-like log ingestion
   - Verifies state changes from events
   - Tests event handlers and projections

4. Process/Workflow Testing
   - Tests temporal workflow triggers
   - Verifies step execution
   - Tests compensation/rollback

Usage:
    # Generate and run all tests
    python -m dazzle.testing.unified_runner ./my-project

    # Generate tests only
    python -m dazzle.testing.dsl_test_generator ./my-project

    # Run existing tests
    python -m dazzle.testing.test_runner ./my-project

    # Run event flow tests
    python -m dazzle.testing.event_test_runner ./my-project
"""

# Curl/bash smoke test generation
from dazzle.testing.curl_test_generator import CurlTestGenerator

# DSL test generation
from dazzle.testing.dsl_test_generator import (
    DSLTestGenerator,
    GeneratedTestSuite,
    TestCoverage,
    generate_tests_from_dsl,
    save_generated_tests,
)
from dazzle.testing.e2e_runner import (
    E2EFlowResult,
    E2ERunner,
    E2ERunOptions,
    E2ERunResult,
    format_e2e_report,
)
from dazzle.testing.event_test_runner import (
    EventLogEntry,
    EventTestCase,
    EventTestCaseResult,
    EventTestResult,
    EventTestRunner,
    EventTestRunResult,
    StateAssertion,
    generate_event_tests_from_appspec,
)
from dazzle.testing.playwright_codegen import (
    generate_test_file,
    generate_test_module,
    generate_tests_for_app,
)
from dazzle.testing.session_manager import (
    PersonaSession,
    SessionManager,
    SessionManifest,
)

# Test runner
from dazzle.testing.test_runner import (
    DazzleClient,
    TestCaseResult,
    TestResult,
    TestRunner,
    TestRunResult,
    format_report,
    run_project_tests,
)
from dazzle.testing.testspec_generator import generate_e2e_testspec
from dazzle.testing.tier2_playwright import (
    DazzleSelector,
    PlaywrightStep,
    PlaywrightTest,
    generate_tier2_test_file,
    generate_tier2_tests,
    generate_tier2_tests_for_app,
)
from dazzle.testing.unified_runner import (
    UnifiedTestResult,
    UnifiedTestRunner,
    format_unified_report,
)
from dazzle.testing.viewport import (
    VIEWPORT_MATRIX,
    ComponentPattern,
    ViewportAssertion,
    ViewportAssertionResult,
    ViewportReport,
    derive_patterns_from_appspec,
)
from dazzle.testing.viewport_runner import (
    ViewportRunner,
    ViewportRunOptions,
    ViewportRunResult,
)

__all__ = [
    # Curl test generator
    "CurlTestGenerator",
    # Playwright codegen
    "generate_test_module",
    "generate_test_file",
    "generate_tests_for_app",
    # Testspec
    "generate_e2e_testspec",
    # Test Runner
    "TestRunner",
    "TestResult",
    "TestCaseResult",
    "TestRunResult",
    "DazzleClient",
    "format_report",
    "run_project_tests",
    # DSL Generator
    "DSLTestGenerator",
    "GeneratedTestSuite",
    "TestCoverage",
    "generate_tests_from_dsl",
    "save_generated_tests",
    # Event Testing
    "EventTestRunner",
    "EventTestCase",
    "EventLogEntry",
    "StateAssertion",
    "EventTestResult",
    "EventTestCaseResult",
    "EventTestRunResult",
    "generate_event_tests_from_appspec",
    # Unified Runner
    "UnifiedTestRunner",
    "UnifiedTestResult",
    "format_unified_report",
    # E2E Runner
    "E2ERunner",
    "E2ERunOptions",
    "E2ERunResult",
    "E2EFlowResult",
    "format_e2e_report",
    # Session Manager
    "SessionManager",
    "PersonaSession",
    "SessionManifest",
    # Tier 2 Playwright Generator
    "DazzleSelector",
    "PlaywrightStep",
    "PlaywrightTest",
    "generate_tier2_tests",
    "generate_tier2_test_file",
    "generate_tier2_tests_for_app",
    # Viewport Testing
    "VIEWPORT_MATRIX",
    "ViewportAssertion",
    "ComponentPattern",
    "ViewportAssertionResult",
    "ViewportReport",
    "derive_patterns_from_appspec",
    "ViewportRunOptions",
    "ViewportRunResult",
    "ViewportRunner",
]
