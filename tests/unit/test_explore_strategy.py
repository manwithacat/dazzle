"""Unit tests for /ux-cycle Strategy.EXPLORE wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.agent.missions.ux_explore import Strategy
from dazzle.core.ir.personas import PersonaSpec

# ----- Fake infrastructure ---------------------------------------------------


class _FakeTranscript:
    """Shape-compatible stand-in for ``AgentTranscript``."""

    def __init__(self, outcome: str = "completed", steps: int = 3, tokens: int = 1500):
        self.outcome = outcome
        self.steps = [MagicMock() for _ in range(steps)]
        self.tokens_used = tokens


class _FakeAgent:
    """Fake ``DazzleAgent`` whose ``run`` invokes each mission tool once.

    The real ``DazzleAgent`` owns an LLM loop we cannot exercise in a unit
    test. This fake takes the mission's tool list and invokes each tool's
    handler with deterministic arguments, which is enough to let the real
    ``propose_component`` / ``record_edge_case`` handlers populate their
    captured ``proposals`` / ``findings`` lists. That is the exact side
    effect ``explore_strategy`` cares about.
    """

    instances: list[_FakeAgent] = []

    def __init__(
        self,
        observer: Any,
        executor: Any,
        use_tool_calls: bool = False,
        mcp_session: Any = None,
    ) -> None:
        # Record constructor args so tests can assert tool-use was requested.
        self.observer = observer
        self.executor = executor
        self.use_tool_calls = use_tool_calls
        self.mcp_session = mcp_session
        _FakeAgent.instances.append(self)

    async def run(self, mission: Any, on_step: Any = None) -> _FakeTranscript:
        for tool in mission.tools:
            # Build deterministic args honouring the tool's declared schema.
            args = _fake_args_for_tool(tool.name, mission.context.get("persona_id", "unknown"))
            tool.handler(args)
        return _FakeTranscript(outcome="completed", steps=len(mission.tools) + 1, tokens=2500)


def _fake_args_for_tool(tool_name: str, persona_id: str) -> dict[str, Any]:
    if tool_name == "propose_component":
        return {
            "component_name": f"proposed-{persona_id}",
            "description": "A hypothetical widget observed during the test.",
            "example_app": "contact_manager",
        }
    if tool_name == "record_edge_case":
        return {
            "component_name": f"edge-{persona_id}",
            "description": "Empty state interaction glitch.",
            "example_app": "contact_manager",
            "severity": "minor",
        }
    raise AssertionError(f"unexpected tool in explore mission: {tool_name}")


def _fake_app_spec(persona_ids: list[str]) -> MagicMock:
    """Minimal AppSpec stand-in with a ``personas`` iterable."""
    spec = MagicMock()
    spec.personas = [PersonaSpec(id=pid, label=pid.capitalize()) for pid in persona_ids]
    return spec


def _fake_bundle_and_connection() -> tuple[MagicMock, MagicMock]:
    """Build a mock Playwright bundle and an AppConnection."""
    from dazzle.qa.server import AppConnection

    bundle = MagicMock()
    bundle.close = AsyncMock()
    bundle.page = MagicMock()
    bundle.browser = MagicMock()
    # ``new_context`` returns an object with ``new_page`` and ``close``
    fake_context = MagicMock()
    fake_context.new_page = AsyncMock(return_value=MagicMock())
    fake_context.close = AsyncMock()
    bundle.browser.new_context = AsyncMock(return_value=fake_context)

    connection = MagicMock(spec=AppConnection)
    connection.site_url = "http://localhost:3000"
    connection.api_url = "http://localhost:8000"
    return bundle, connection


# ----- Tests -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_fake_agent_instances() -> None:
    _FakeAgent.instances = []
    yield
    _FakeAgent.instances = []


@pytest.mark.asyncio
async def test_anonymous_run_builds_missing_contracts_mission(tmp_path: Path) -> None:
    """personas=[] runs one anonymous cycle and returns proposals."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
        run_explore_strategy,
    )

    bundle, connection = _fake_bundle_and_connection()
    fake_spec = _fake_app_spec(persona_ids=["admin", "user"])

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.setup_playwright",
            new=AsyncMock(return_value=bundle),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.load_project_appspec",
            return_value=fake_spec,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.DazzleAgent",
            new=_FakeAgent,
        ),
    ):
        outcome = await run_explore_strategy(
            connection,
            example_root=tmp_path / "examples" / "contact_manager",
            strategy=Strategy.MISSING_CONTRACTS,
            personas=[],  # explicit anonymous escape hatch (cycle 197: None now means auto-pick)
        )

    assert outcome.degraded is False
    assert len(outcome.proposals) == 1
    assert outcome.proposals[0]["component_name"] == "proposed-anonymous"
    assert outcome.proposals[0]["persona_id"] is None
    assert "1 persona(s)" in outcome.summary
    assert len(_FakeAgent.instances) == 1
    assert _FakeAgent.instances[0].use_tool_calls is True
    bundle.close.assert_awaited_once()
    # No fresh context was created because personas=[] reuses the bundle page
    bundle.browser.new_context.assert_not_called()


@pytest.mark.asyncio
async def test_multi_persona_run_aggregates_proposals(tmp_path: Path) -> None:
    """personas=[admin, user] runs once per persona and sums proposals."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
        run_explore_strategy,
    )

    bundle, connection = _fake_bundle_and_connection()
    fake_spec = _fake_app_spec(persona_ids=["admin", "user"])

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.setup_playwright",
            new=AsyncMock(return_value=bundle),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.load_project_appspec",
            return_value=fake_spec,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.login_as_persona",
            new=AsyncMock(),
        ) as mock_login,
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.DazzleAgent",
            new=_FakeAgent,
        ),
    ):
        outcome = await run_explore_strategy(
            connection,
            example_root=tmp_path / "examples" / "contact_manager",
            strategy=Strategy.MISSING_CONTRACTS,
            personas=["admin", "user"],
        )

    assert outcome.degraded is False
    assert len(outcome.proposals) == 2
    personas_seen = {p["persona_id"] for p in outcome.proposals}
    assert personas_seen == {"admin", "user"}
    assert mock_login.await_count == 2
    # One agent per persona
    assert len(_FakeAgent.instances) == 2
    assert bundle.browser.new_context.await_count == 2


@pytest.mark.asyncio
async def test_edge_cases_strategy_populates_findings(tmp_path: Path) -> None:
    """Strategy.EDGE_CASES uses record_edge_case and fills findings list."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
        run_explore_strategy,
    )

    bundle, connection = _fake_bundle_and_connection()
    fake_spec = _fake_app_spec(persona_ids=["admin"])

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.setup_playwright",
            new=AsyncMock(return_value=bundle),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.load_project_appspec",
            return_value=fake_spec,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.login_as_persona",
            new=AsyncMock(),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.DazzleAgent",
            new=_FakeAgent,
        ),
    ):
        outcome = await run_explore_strategy(
            connection,
            example_root=tmp_path / "examples" / "contact_manager",
            strategy=Strategy.EDGE_CASES,
            personas=["admin"],
        )

    assert outcome.degraded is False
    assert outcome.proposals == []
    assert len(outcome.findings) == 1
    assert outcome.findings[0]["severity"] == "minor"
    assert outcome.findings[0]["persona_id"] == "admin"
    assert outcome.strategy == "EXPLORE/edge_cases"


@pytest.mark.asyncio
async def test_one_persona_blocked_does_not_abort_others(tmp_path: Path) -> None:
    """A per-persona login failure records BLOCKED but other personas still run."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
        run_explore_strategy,
    )

    bundle, connection = _fake_bundle_and_connection()
    fake_spec = _fake_app_spec(persona_ids=["admin", "user"])

    # First call raises (admin), second call succeeds (user)
    login_mock = AsyncMock(side_effect=[RuntimeError("login rejected"), None])

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.setup_playwright",
            new=AsyncMock(return_value=bundle),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.load_project_appspec",
            return_value=fake_spec,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.login_as_persona",
            new=login_mock,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.DazzleAgent",
            new=_FakeAgent,
        ),
    ):
        outcome = await run_explore_strategy(
            connection,
            example_root=tmp_path / "examples" / "contact_manager",
            strategy=Strategy.MISSING_CONTRACTS,
            personas=["admin", "user"],
        )

    assert outcome.degraded is True
    assert len(outcome.blocked_personas) == 1
    assert outcome.blocked_personas[0][0] == "admin"
    assert "login rejected" in outcome.blocked_personas[0][1]
    # user still produced a proposal
    assert len(outcome.proposals) == 1
    assert outcome.proposals[0]["persona_id"] == "user"


@pytest.mark.asyncio
async def test_all_personas_blocked_raises(tmp_path: Path) -> None:
    """If every persona is blocked, the strategy raises rather than returning."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
        run_explore_strategy,
    )

    bundle, connection = _fake_bundle_and_connection()
    fake_spec = _fake_app_spec(persona_ids=["admin"])

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.setup_playwright",
            new=AsyncMock(return_value=bundle),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.load_project_appspec",
            return_value=fake_spec,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.login_as_persona",
            new=AsyncMock(side_effect=RuntimeError("magic-link 404")),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.DazzleAgent",
            new=_FakeAgent,
        ),
        pytest.raises(RuntimeError, match="all personas blocked"),
    ):
        await run_explore_strategy(
            connection,
            example_root=tmp_path / "examples" / "contact_manager",
            strategy=Strategy.MISSING_CONTRACTS,
            personas=["admin"],
        )

    # Bundle still torn down even though strategy raised
    bundle.close.assert_awaited_once()


# ----- TestPickExplorePersonas -----------------------------------------------


def _make_app_spec_with_personas(personas_list: list[PersonaSpec]) -> MagicMock:
    spec = MagicMock()
    spec.personas = personas_list
    return spec


class TestPickExplorePersonas:
    def test_filters_platform_personas_out(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_explore_personas,
        )

        spec = _make_app_spec_with_personas(
            [
                PersonaSpec(id="admin", label="Admin", default_workspace="_platform_admin"),
                PersonaSpec(id="user", label="User", default_workspace="contacts"),
            ]
        )
        result = pick_explore_personas(spec)
        assert len(result) == 1
        assert result[0].id == "user"

    def test_sorts_business_personas_alphabetically(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_explore_personas,
        )

        spec = _make_app_spec_with_personas(
            [
                PersonaSpec(id="manager", label="M", default_workspace="my_work"),
                PersonaSpec(id="admin", label="A", default_workspace="admin_dashboard"),
                PersonaSpec(id="user", label="U", default_workspace="my_work"),
            ]
        )
        result = pick_explore_personas(spec)
        assert [p.id for p in result] == ["admin", "manager", "user"]

    def test_override_returns_in_caller_order(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_explore_personas,
        )

        spec = _make_app_spec_with_personas(
            [
                PersonaSpec(id="admin", label="A", default_workspace="_platform_admin"),
                PersonaSpec(id="customer", label="C", default_workspace="store"),
                PersonaSpec(id="agent", label="Ag", default_workspace="support"),
            ]
        )
        result = pick_explore_personas(spec, override=["customer", "admin"])
        assert [p.id for p in result] == ["customer", "admin"]

    def test_override_unknown_id_raises_value_error(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_explore_personas,
        )

        spec = _make_app_spec_with_personas(
            [PersonaSpec(id="user", label="U", default_workspace="x")]
        )
        with pytest.raises(ValueError, match="persona 'nobody' not found"):
            pick_explore_personas(spec, override=["nobody"])

    def test_all_platform_personas_returns_empty_list(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_explore_personas,
        )

        spec = _make_app_spec_with_personas(
            [
                PersonaSpec(id="admin", label="A", default_workspace="_platform_admin"),
                PersonaSpec(id="sys", label="S", default_workspace="_system"),
            ]
        )
        result = pick_explore_personas(spec)
        assert result == []

    def test_persona_with_no_default_workspace_is_kept(self) -> None:
        """Personas without default_workspace are not framework-scoped."""
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_explore_personas,
        )

        spec = _make_app_spec_with_personas(
            [PersonaSpec(id="visitor", label="V", default_workspace=None)]
        )
        result = pick_explore_personas(spec)
        assert len(result) == 1
        assert result[0].id == "visitor"


@pytest.mark.asyncio
async def test_bundle_closed_even_when_agent_raises(tmp_path: Path) -> None:
    """Bundle teardown runs in the outer finally regardless of per-run errors."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
        run_explore_strategy,
    )

    bundle, connection = _fake_bundle_and_connection()
    fake_spec = _fake_app_spec(persona_ids=["admin"])

    class _RaisingAgent(_FakeAgent):
        async def run(self, mission: Any, on_step: Any = None) -> _FakeTranscript:
            raise RuntimeError("agent crashed")

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.setup_playwright",
            new=AsyncMock(return_value=bundle),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.load_project_appspec",
            return_value=fake_spec,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.login_as_persona",
            new=AsyncMock(),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.DazzleAgent",
            new=_RaisingAgent,
        ),
        pytest.raises(RuntimeError, match="all personas blocked"),
    ):
        await run_explore_strategy(
            connection,
            example_root=tmp_path / "examples" / "contact_manager",
            strategy=Strategy.MISSING_CONTRACTS,
            personas=["admin"],
        )

    bundle.close.assert_awaited_once()


class TestPickStartPath:
    def test_uses_explicit_default_route(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_start_path,
        )

        persona = PersonaSpec(
            id="user",
            label="U",
            default_workspace="contacts",
            default_route="/app/workspaces/contacts",
        )
        spec = MagicMock()
        spec.workspaces = []

        with patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.compute_persona_default_routes",
            return_value={"user": "/app/workspaces/contacts"},
        ):
            result = pick_start_path(persona, spec)
        assert result == "/app/workspaces/contacts"

    def test_falls_back_to_app_when_no_route(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_start_path,
        )

        persona = PersonaSpec(id="nobody", label="N")
        spec = MagicMock()
        spec.workspaces = []

        with patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.compute_persona_default_routes",
            return_value={},  # helper found nothing
        ):
            result = pick_start_path(persona, spec)
        assert result == "/app"

    def test_delegates_to_compute_persona_default_routes(self) -> None:
        """Verify we call into the shared helper with the right shape."""
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            pick_start_path,
        )

        persona = PersonaSpec(id="user", label="U", default_workspace="contacts")
        spec = MagicMock()
        spec.workspaces = ["ws-sentinel"]

        with patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.compute_persona_default_routes",
            return_value={"user": "/app/contacts"},
        ) as mock_compute:
            result = pick_start_path(persona, spec)

        mock_compute.assert_called_once_with(personas=[persona], workspaces=["ws-sentinel"])
        assert result == "/app/contacts"


class TestProposalDedup:
    def test_same_component_across_personas_merges(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            _dedup_proposals,
        )

        raw = [
            {
                "component_name": "contact-card",
                "description": "A card showing a contact.",
                "example_app": "contact_manager",
                "persona_id": "user",
            },
            {
                "component_name": "contact-card",
                "description": "A different description.",
                "example_app": "contact_manager",
                "persona_id": "manager",
            },
        ]
        deduped = _dedup_proposals(raw)
        assert len(deduped) == 1
        assert deduped[0]["component_name"] == "contact-card"
        # First description wins
        assert deduped[0]["description"] == "A card showing a contact."
        assert deduped[0]["contributing_personas"] == ["user", "manager"]

    def test_dedup_is_case_insensitive(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            _dedup_proposals,
        )

        raw = [
            {
                "component_name": "Contact-Card",
                "description": "x",
                "example_app": "a",
                "persona_id": "u1",
            },
            {
                "component_name": "contact-card",
                "description": "y",
                "example_app": "a",
                "persona_id": "u2",
            },
        ]
        deduped = _dedup_proposals(raw)
        assert len(deduped) == 1
        assert deduped[0]["contributing_personas"] == ["u1", "u2"]

    def test_different_apps_do_not_dedup(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            _dedup_proposals,
        )

        raw = [
            {"component_name": "card", "description": "x", "example_app": "a", "persona_id": "u1"},
            {"component_name": "card", "description": "y", "example_app": "b", "persona_id": "u2"},
        ]
        deduped = _dedup_proposals(raw)
        assert len(deduped) == 2

    def test_single_persona_contributing_list(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            _dedup_proposals,
        )

        raw = [
            {"component_name": "card", "description": "x", "example_app": "a", "persona_id": "u1"},
        ]
        deduped = _dedup_proposals(raw)
        assert deduped[0]["contributing_personas"] == ["u1"]


class TestExploreOutcomeShape:
    def test_has_raw_proposals_by_persona_field(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            ExploreOutcome,
        )

        outcome = ExploreOutcome(
            strategy="EXPLORE/missing_contracts",
            summary="test",
            degraded=False,
        )
        assert outcome.raw_proposals_by_persona == {}

    def test_raw_proposals_by_persona_populated(self) -> None:
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            ExploreOutcome,
        )

        outcome = ExploreOutcome(
            strategy="EXPLORE/missing_contracts",
            summary="test",
            degraded=False,
            raw_proposals_by_persona={"user": 3, "manager": 2},
        )
        assert outcome.raw_proposals_by_persona == {"user": 3, "manager": 2}


class TestRunExploreStrategyFanOut:
    @pytest.mark.asyncio
    async def test_personas_none_triggers_auto_pick(self, tmp_path: Path) -> None:
        """personas=None runs once per auto-picked business persona."""
        from dazzle.agent.missions.ux_explore import Strategy
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            run_explore_strategy,
        )

        bundle, connection = _fake_bundle_and_connection()
        # AppSpec with 2 business personas + 1 platform persona
        fake_spec = MagicMock()
        fake_spec.personas = [
            PersonaSpec(id="admin", label="A", default_workspace="_platform_admin"),
            PersonaSpec(id="manager", label="M", default_workspace="my_work"),
            PersonaSpec(id="member", label="Mem", default_workspace="my_work"),
        ]
        fake_spec.workspaces = []

        with (
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.setup_playwright",
                new=AsyncMock(return_value=bundle),
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.load_project_appspec",
                return_value=fake_spec,
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.login_as_persona",
                new=AsyncMock(),
            ) as mock_login,
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.compute_persona_default_routes",
                return_value={"manager": "/app/m", "member": "/app/mem"},
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.DazzleAgent",
                new=_FakeAgent,
            ),
        ):
            await run_explore_strategy(
                connection,
                example_root=tmp_path / "example",
                strategy=Strategy.MISSING_CONTRACTS,
                personas=None,  # auto-pick
            )

        # Should have run once per business persona (2 total — admin is platform-scoped)
        assert mock_login.await_count == 2
        assert len(_FakeAgent.instances) == 2

    @pytest.mark.asyncio
    async def test_personas_empty_list_runs_anonymously(self, tmp_path: Path) -> None:
        """personas=[] still means anonymous (backwards compat escape hatch)."""
        from dazzle.agent.missions.ux_explore import Strategy
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            run_explore_strategy,
        )

        bundle, connection = _fake_bundle_and_connection()
        fake_spec = MagicMock()
        fake_spec.personas = [
            PersonaSpec(id="member", label="Mem", default_workspace="my_work"),
        ]
        fake_spec.workspaces = []

        with (
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.setup_playwright",
                new=AsyncMock(return_value=bundle),
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.load_project_appspec",
                return_value=fake_spec,
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.login_as_persona",
                new=AsyncMock(),
            ) as mock_login,
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.DazzleAgent",
                new=_FakeAgent,
            ),
        ):
            await run_explore_strategy(
                connection,
                example_root=tmp_path / "example",
                strategy=Strategy.MISSING_CONTRACTS,
                personas=[],  # explicit empty = anonymous
            )

        # No login call — anonymous path
        assert mock_login.await_count == 0
        assert len(_FakeAgent.instances) == 1  # one anonymous run

    @pytest.mark.asyncio
    async def test_fan_out_populates_raw_proposals_by_persona(self, tmp_path: Path) -> None:
        """raw_proposals_by_persona tracks pre-dedup counts per persona."""
        from dazzle.agent.missions.ux_explore import Strategy
        from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
            run_explore_strategy,
        )

        bundle, connection = _fake_bundle_and_connection()
        fake_spec = MagicMock()
        fake_spec.personas = [
            PersonaSpec(id="manager", label="M", default_workspace="my_work"),
            PersonaSpec(id="member", label="Mem", default_workspace="my_work"),
        ]
        fake_spec.workspaces = []

        with (
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.setup_playwright",
                new=AsyncMock(return_value=bundle),
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.load_project_appspec",
                return_value=fake_spec,
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.login_as_persona",
                new=AsyncMock(),
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.compute_persona_default_routes",
                return_value={"manager": "/app", "member": "/app"},
            ),
            patch(
                "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.DazzleAgent",
                new=_FakeAgent,
            ),
        ):
            outcome = await run_explore_strategy(
                connection,
                example_root=tmp_path / "example",
                strategy=Strategy.MISSING_CONTRACTS,
                personas=None,
            )

        # _FakeAgent produces one proposal per persona (with a persona-tagged component name)
        # With our two personas the deduped list should have 2 entries (different names).
        # raw_proposals_by_persona tracks the pre-dedup counts.
        assert outcome.raw_proposals_by_persona == {"manager": 1, "member": 1}
