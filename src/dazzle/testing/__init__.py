"""DAZZLE testing framework.

Test infrastructure for DAZZLE applications, imported by submodule (this
package re-exports nothing):

- ``testspec_generator`` / ``test_runner`` / ``step_executor`` — E2ETestSpec
  generation and API-tier execution (``dazzle test generate|run``)
- ``dsl_test_generator`` / ``unified_runner`` — DSL-driven test generation and
  execution (``dazzle test dsl-run``, ``tier2-generate``)
- ``tier2_playwright`` / ``e2e_runner`` / ``agent_e2e`` — Playwright and
  LLM-agent tiers
- ``session_manager`` / ``entity_client`` — persona sessions and HTTP clients
- ``walk`` — story-linked scene walks (``dazzle test walk``)
- ``ux`` — deterministic UX verification (``dazzle ux verify``)
"""
