"""Task 20 — /ux-cycle Strategy.FITNESS integration test."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_fitness_strategy_calls_engine_run(tmp_path: Path) -> None:
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )

    fake_engine = MagicMock()
    fake_engine.run = AsyncMock(
        return_value=MagicMock(
            findings=[],
            profile=MagicMock(degraded=False),
            independence_jaccard=0.4,
            run_metadata={"run_id": "r1"},
        )
    )
    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")
    fake_bundle = MagicMock()
    fake_bundle.close = AsyncMock()

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._launch_example_app",
            new=AsyncMock(return_value=fake_handle),
        ) as mock_launch,
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._stop_example_app"
        ) as mock_stop,
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._setup_playwright",
            new=AsyncMock(return_value=fake_bundle),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._build_engine",
            new=AsyncMock(return_value=fake_engine),
        ) as mock_build,
    ):
        outcome = await run_fitness_strategy(example_app="support_tickets", project_root=tmp_path)

    assert fake_engine.run.await_count == 1
    assert "r1" in outcome.summary
    assert mock_launch.call_count == 1
    mock_stop.assert_called_once_with(fake_handle)
    assert mock_build.call_count == 1


@pytest.mark.asyncio
async def test_fitness_strategy_records_blocked_outcome_on_engine_failure(tmp_path: Path) -> None:
    """Lifecycle teardown must run even when the engine raises.

    v1.0.3 Task 4: engine run failures are caught and recorded as BLOCKED
    outcomes rather than propagated. The strategy still tears down the
    bundle and subprocess, and returns a degraded StrategyOutcome.
    """
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )

    fake_engine = MagicMock()
    fake_engine.run = AsyncMock(side_effect=RuntimeError("boom"))
    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")
    fake_bundle = MagicMock()
    fake_bundle.close = AsyncMock()

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._launch_example_app",
            new=AsyncMock(return_value=fake_handle),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._stop_example_app"
        ) as mock_stop,
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._setup_playwright",
            new=AsyncMock(return_value=fake_bundle),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._build_engine",
            new=AsyncMock(return_value=fake_engine),
        ),
    ):
        outcome = await run_fitness_strategy(example_app="support_tickets", project_root=tmp_path)

    # Teardown still fires
    mock_stop.assert_called_once_with(fake_handle)
    fake_bundle.close.assert_awaited_once()
    # Engine failure produces a degraded BLOCKED outcome (not a raised exception)
    assert outcome.degraded is True
    assert outcome.findings_count == 0


@pytest.mark.asyncio
async def test_fitness_strategy_stops_app_when_playwright_setup_fails(
    tmp_path: Path,
) -> None:
    """If _setup_playwright raises, _stop_example_app must still run.

    v1.0.3 Task 2 introduced this path (bundle setup moved from _build_engine
    to the strategy). The outer try/finally now owns bundle lifecycle, so
    this test verifies the failure path that used to live inside _build_engine.
    """
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )

    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")

    async def _raising_setup(base_url: str):
        raise RuntimeError("playwright missing")

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._launch_example_app",
            new=AsyncMock(return_value=fake_handle),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._stop_example_app"
        ) as mock_stop,
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._setup_playwright",
            new=_raising_setup,
        ),
        pytest.raises(RuntimeError, match="playwright missing"),
    ):
        await run_fitness_strategy(example_app="support_tickets", project_root=tmp_path)

    # Subprocess teardown must have fired even though playwright setup failed
    mock_stop.assert_called_once_with(fake_handle)


@pytest.mark.asyncio
async def test_launch_example_app_uses_qa_server(tmp_path: Path) -> None:
    """`_launch_example_app` delegates to dazzle.qa.server.connect_app and waits for ready."""
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    example_root = tmp_path / "examples" / "support_tickets"
    example_root.mkdir(parents=True)

    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.connect_app",
            return_value=fake_handle,
        ) as mock_connect,
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.wait_for_ready",
            new=AsyncMock(return_value=True),
        ) as mock_wait,
    ):
        result = await fitness_strategy._launch_example_app(example_root=example_root)

    assert result is fake_handle
    mock_connect.assert_called_once_with(project_dir=example_root)
    mock_wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_launch_example_app_raises_on_health_timeout(tmp_path: Path) -> None:
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    example_root = tmp_path / "examples" / "support_tickets"
    example_root.mkdir(parents=True)

    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.connect_app",
            return_value=fake_handle,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.wait_for_ready",
            new=AsyncMock(return_value=False),
        ),
        pytest.raises(RuntimeError, match="did not become ready"),
    ):
        await fitness_strategy._launch_example_app(example_root=example_root)

    # Teardown must fire even on failed launch.
    fake_handle.stop.assert_called_once()


@pytest.mark.asyncio
async def test_launch_example_app_stops_handle_on_wait_exception(tmp_path: Path) -> None:
    """If wait_for_ready raises, the handle must be torn down before the exception propagates."""
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    example_root = tmp_path / "examples" / "support_tickets"
    example_root.mkdir(parents=True)

    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.connect_app",
            return_value=fake_handle,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.wait_for_ready",
            new=AsyncMock(side_effect=OSError("connection refused")),
        ),
        pytest.raises(OSError, match="connection refused"),
    ):
        await fitness_strategy._launch_example_app(example_root=example_root)

    fake_handle.stop.assert_called_once()


def test_stop_example_app_calls_handle_stop() -> None:
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    handle = MagicMock()
    fitness_strategy._stop_example_app(handle)
    handle.stop.assert_called_once()


@pytest.mark.asyncio
async def test_build_engine_wires_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_build_engine` assembles AppSpec + FitnessConfig + agent + snapshot source + LLM."""
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    example_root = tmp_path / "examples" / "support_tickets"
    example_root.mkdir(parents=True)
    (example_root / "SPEC.md").write_text("# spec\n")

    monkeypatch.setenv("DATABASE_URL", "postgresql://stub")

    fake_app_spec = MagicMock(entities=[], stories=[], personas=[])
    fake_config = MagicMock()
    fake_engine = MagicMock()
    fake_engine.run = AsyncMock(
        return_value=MagicMock(
            findings=[],
            profile=MagicMock(degraded=False),
            independence_jaccard=0.0,
            run_metadata={"run_id": "r1"},
        )
    )

    fake_bundle = MagicMock()
    fake_bundle.page = MagicMock()
    fake_bundle.page.goto = AsyncMock()

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.load_project_appspec",
            return_value=fake_app_spec,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.load_fitness_config",
            return_value=fake_config,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.PostgresBackend"
        ) as mock_backend,
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.LLMAPIClient") as mock_llm,
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.FitnessEngine",
            return_value=fake_engine,
        ) as mock_engine_cls,
    ):
        handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")
        await fitness_strategy._build_engine(
            example_root=example_root,
            handle=handle,
            bundle=fake_bundle,
            component_contract_path=None,
        )

    mock_backend.assert_called_once_with(database_url="postgresql://stub")
    mock_llm.assert_called_once_with()
    mock_engine_cls.assert_called_once()


@pytest.mark.asyncio
async def test_build_engine_raises_when_database_url_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    example_root = tmp_path / "examples" / "support_tickets"
    example_root.mkdir(parents=True)
    (example_root / "SPEC.md").write_text("# spec\n")

    monkeypatch.delenv("DATABASE_URL", raising=False)

    fake_bundle = MagicMock()

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        await fitness_strategy._build_engine(
            example_root=example_root,
            handle=MagicMock(site_url="http://x", api_url="http://y"),
            bundle=fake_bundle,
            component_contract_path=None,
        )


@pytest.mark.asyncio
async def test_build_engine_passes_contract_path_to_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_build_engine` with a contract_path constructs FitnessEngine with contract_paths set."""
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    example_root = tmp_path / "examples" / "support_tickets"
    example_root.mkdir(parents=True)
    (example_root / "SPEC.md").write_text("# spec\n")

    contract_path = tmp_path / "auth-page.md"
    contract_path.write_text("# auth-page\n\n## Quality Gates\n\n1. Card centered\n")

    monkeypatch.setenv("DATABASE_URL", "postgresql://stub")

    fake_bundle = MagicMock()
    fake_bundle.page = MagicMock()
    fake_bundle.page.goto = AsyncMock()

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.load_project_appspec",
            return_value=MagicMock(entities=[], stories=[], personas=[]),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.load_fitness_config",
            return_value=MagicMock(),
        ),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.PostgresBackend"),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.LLMAPIClient"),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.FitnessEngine",
        ) as mock_engine_cls,
    ):
        handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")
        await fitness_strategy._build_engine(
            example_root=example_root,
            handle=handle,
            bundle=fake_bundle,
            component_contract_path=contract_path,
        )

    mock_engine_cls.assert_called_once()
    call_kwargs = mock_engine_cls.call_args.kwargs
    assert call_kwargs["contract_paths"] == [contract_path]
    assert call_kwargs["contract_observer"] is not None


@pytest.mark.asyncio
async def test_run_fitness_strategy_threads_contract_path(
    tmp_path: Path,
) -> None:
    """run_fitness_strategy forwards component_contract_path to _build_engine."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )

    fake_engine = MagicMock()
    fake_engine.run = AsyncMock(
        return_value=MagicMock(
            findings=[],
            profile=MagicMock(degraded=False),
            independence_jaccard=0.0,
            run_metadata={"run_id": "r2"},
        )
    )
    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")

    contract_path = tmp_path / "auth-page.md"
    contract_path.write_text("# auth-page\n\n## Quality Gates\n\n1. gate\n")

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._launch_example_app",
            new=AsyncMock(return_value=fake_handle),
        ),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._stop_example_app"),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._build_engine",
            new=AsyncMock(return_value=fake_engine),
        ) as mock_build,
    ):
        await run_fitness_strategy(
            example_app="support_tickets",
            project_root=tmp_path,
            component_contract_path=contract_path,
        )

    mock_build.assert_awaited_once()
    build_kwargs = mock_build.call_args.kwargs
    assert build_kwargs["component_contract_path"] == contract_path


@pytest.mark.asyncio
async def test_build_engine_takes_prebuilt_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_build_engine now accepts a bundle parameter instead of creating its own."""
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    example_root = tmp_path / "examples" / "support_tickets"
    example_root.mkdir(parents=True)
    (example_root / "SPEC.md").write_text("# spec\n")

    monkeypatch.setenv("DATABASE_URL", "postgresql://stub")

    fake_bundle = MagicMock()
    fake_bundle.page = MagicMock()
    fake_bundle.page.goto = AsyncMock()

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.load_project_appspec",
            return_value=MagicMock(entities=[], stories=[], personas=[]),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.load_fitness_config",
            return_value=MagicMock(),
        ),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.PostgresBackend"),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.LLMAPIClient"),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.FitnessEngine",
        ) as mock_engine_cls,
    ):
        handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")
        result = await fitness_strategy._build_engine(
            example_root=example_root,
            handle=handle,
            bundle=fake_bundle,
            component_contract_path=None,
        )

    # Engine was constructed with the injected bundle's page (not a new bundle)
    mock_engine_cls.assert_called_once()
    # The returned object is the engine itself (or a proxy), not something that closes the bundle
    assert result is not None


@pytest.mark.asyncio
async def test_build_engine_navigates_to_contract_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the contract has an anchor, _build_engine navigates the page before building."""
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    example_root = tmp_path / "examples" / "support_tickets"
    example_root.mkdir(parents=True)
    (example_root / "SPEC.md").write_text("# spec\n")

    contract_path = tmp_path / "auth-page.md"
    contract_path.write_text(
        "# auth-page\n\n## Anchor\n\n/login\n\n## Quality Gates\n\n1. Card centered\n"
    )

    monkeypatch.setenv("DATABASE_URL", "postgresql://stub")

    fake_bundle = MagicMock()
    fake_bundle.page = MagicMock()
    fake_bundle.page.goto = AsyncMock()

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.load_project_appspec",
            return_value=MagicMock(entities=[], stories=[], personas=[]),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.load_fitness_config",
            return_value=MagicMock(),
        ),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.PostgresBackend"),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.LLMAPIClient"),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.FitnessEngine",
        ),
    ):
        handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")
        await fitness_strategy._build_engine(
            example_root=example_root,
            handle=handle,
            bundle=fake_bundle,
            component_contract_path=contract_path,
        )

    # Page was navigated to site_url + anchor
    fake_bundle.page.goto.assert_awaited_once_with("http://localhost:3000/login")


@pytest.mark.asyncio
async def test_build_engine_does_not_navigate_when_no_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the contract has no anchor, _build_engine skips navigation (v1.0.2 behavior)."""
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    example_root = tmp_path / "examples" / "support_tickets"
    example_root.mkdir(parents=True)
    (example_root / "SPEC.md").write_text("# spec\n")

    contract_path = tmp_path / "no-anchor.md"
    contract_path.write_text("# no-anchor\n\n## Quality Gates\n\n1. gate\n")

    monkeypatch.setenv("DATABASE_URL", "postgresql://stub")

    fake_bundle = MagicMock()
    fake_bundle.page = MagicMock()
    fake_bundle.page.goto = AsyncMock()

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.load_project_appspec",
            return_value=MagicMock(entities=[], stories=[], personas=[]),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.load_fitness_config",
            return_value=MagicMock(),
        ),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.PostgresBackend"),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.LLMAPIClient"),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.FitnessEngine",
        ),
    ):
        handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")
        await fitness_strategy._build_engine(
            example_root=example_root,
            handle=handle,
            bundle=fake_bundle,
            component_contract_path=contract_path,
        )

    # No navigation happened
    fake_bundle.page.goto.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_engine_normalizes_anchor_without_leading_slash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anchors written without a leading / still produce well-formed URLs."""
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    example_root = tmp_path / "examples" / "support_tickets"
    example_root.mkdir(parents=True)
    (example_root / "SPEC.md").write_text("# spec\n")

    # Anchor body has NO leading slash
    contract_path = tmp_path / "slashless.md"
    contract_path.write_text("# slashless\n\n## Anchor\n\nlogin\n\n## Quality Gates\n\n1. gate\n")

    monkeypatch.setenv("DATABASE_URL", "postgresql://stub")

    fake_bundle = MagicMock()
    fake_bundle.page = MagicMock()
    fake_bundle.page.goto = AsyncMock()

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.load_project_appspec",
            return_value=MagicMock(entities=[], stories=[], personas=[]),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.load_fitness_config",
            return_value=MagicMock(),
        ),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.PostgresBackend"),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.LLMAPIClient"),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy.FitnessEngine",
        ),
    ):
        handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")
        await fitness_strategy._build_engine(
            example_root=example_root,
            handle=handle,
            bundle=fake_bundle,
            component_contract_path=contract_path,
        )

    # Even though the contract wrote "login" without a leading slash, the URL is well-formed
    fake_bundle.page.goto.assert_awaited_once_with("http://localhost:3000/login")


@pytest.mark.asyncio
async def test_login_as_persona_happy_path() -> None:
    """_login_as_persona calls POST /qa/magic-link then navigates /auth/magic/{token}.

    The QA endpoint returns MagicLinkResponse(url="/auth/magic/<token>") — a
    server-relative path keyed as "url", not "token".  The POST must be JSON
    with an explicit Content-Type header so the Pydantic body model accepts it.
    """
    import json as _json

    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    fake_response = MagicMock()
    fake_response.ok = True
    fake_response.status = 200
    fake_response.json = AsyncMock(return_value={"url": "/auth/magic/abc123"})

    fake_request = MagicMock()
    fake_request.post = AsyncMock(return_value=fake_response)

    fake_page = MagicMock()
    fake_page.request = fake_request
    fake_page.goto = AsyncMock()
    fake_page.url = "http://localhost:3000/"  # after-login state

    await fitness_strategy._login_as_persona(
        page=fake_page,
        persona_id="admin",
        api_url="http://localhost:8000",
    )

    fake_request.post.assert_awaited_once_with(
        "http://localhost:8000/qa/magic-link",
        data=_json.dumps({"persona_id": "admin"}),
        headers={"Content-Type": "application/json"},
    )
    fake_page.goto.assert_awaited_once_with("http://localhost:8000/auth/magic/abc123?next=/")


@pytest.mark.asyncio
async def test_login_as_persona_raises_when_qa_mode_disabled() -> None:
    """If POST /qa/magic-link returns 404, raise with a helpful hint about
    DAZZLE_QA_MODE flags + persona provisioning (both are possible 404 causes
    per qa_routes.py:59,65)."""
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    fake_response = MagicMock()
    fake_response.ok = False
    fake_response.status = 404

    fake_request = MagicMock()
    fake_request.post = AsyncMock(return_value=fake_response)

    fake_page = MagicMock()
    fake_page.request = fake_request

    with pytest.raises(RuntimeError, match="magic-link endpoint returned 404"):
        await fitness_strategy._login_as_persona(
            page=fake_page,
            persona_id="admin",
            api_url="http://localhost:8000",
        )


@pytest.mark.asyncio
async def test_login_as_persona_raises_when_magic_link_generation_fails() -> None:
    """If POST /qa/magic-link returns another 4xx/5xx, raise with the status code."""
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    fake_response = MagicMock()
    fake_response.ok = False
    fake_response.status = 500

    fake_request = MagicMock()
    fake_request.post = AsyncMock(return_value=fake_response)

    fake_page = MagicMock()
    fake_page.request = fake_request

    with pytest.raises(RuntimeError, match="magic-link generation failed: HTTP 500"):
        await fitness_strategy._login_as_persona(
            page=fake_page,
            persona_id="admin",
            api_url="http://localhost:8000",
        )


@pytest.mark.asyncio
async def test_login_as_persona_raises_when_token_rejected() -> None:
    """If after goto the page path is /auth/login, the token was rejected.

    Uses the real failure URL from magic_link_routes.py:54,62 for fidelity
    with the production server response.
    """
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    fake_response = MagicMock()
    fake_response.ok = True
    fake_response.status = 200
    fake_response.json = AsyncMock(return_value={"url": "/auth/magic/expired"})

    fake_request = MagicMock()
    fake_request.post = AsyncMock(return_value=fake_response)

    fake_page = MagicMock()
    fake_page.request = fake_request
    fake_page.goto = AsyncMock()
    fake_page.url = "http://localhost:3000/auth/login?error=invalid_magic_link"

    with pytest.raises(RuntimeError, match="persona login rejected"):
        await fitness_strategy._login_as_persona(
            page=fake_page,
            persona_id="admin",
            api_url="http://localhost:8000",
        )


@pytest.mark.asyncio
async def test_login_as_persona_does_not_false_positive_on_login_substring() -> None:
    """URL containing 'login' as a substring but not as a path does NOT raise.

    Regression guard for the tightened path-exact login-rejection check.
    /app/logins contains "login" but is not a login redirect target.
    """
    from dazzle.cli.runtime_impl.ux_cycle_impl import fitness_strategy

    fake_response = MagicMock()
    fake_response.ok = True
    fake_response.status = 200
    fake_response.json = AsyncMock(return_value={"url": "/auth/magic/ok"})

    fake_request = MagicMock()
    fake_request.post = AsyncMock(return_value=fake_response)

    fake_page = MagicMock()
    fake_page.request = fake_request
    fake_page.goto = AsyncMock()
    # URL contains "login" as a substring but the path is /app/logins
    fake_page.url = "http://localhost:3000/app/logins"

    # Should NOT raise — /app/logins is not a login page
    await fitness_strategy._login_as_persona(
        page=fake_page,
        persona_id="admin",
        api_url="http://localhost:8000",
    )


@pytest.mark.asyncio
async def test_run_fitness_strategy_multi_persona_creates_fresh_context_per_persona(
    tmp_path: Path,
) -> None:
    """Each named persona gets a fresh browser.new_context(). The shared browser is reused."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )

    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")

    fake_engine = MagicMock()
    fake_engine.run = AsyncMock(
        return_value=MagicMock(
            findings=[],
            profile=MagicMock(degraded=False),
            independence_jaccard=0.5,
            run_metadata={"run_id": "rX"},
        )
    )

    fresh_contexts: list[Any] = []

    async def _fake_new_context(**kwargs: Any) -> Any:
        new_ctx = MagicMock()
        new_ctx.new_page = AsyncMock(return_value=MagicMock(url="http://localhost:3000/"))
        new_ctx.close = AsyncMock()
        fresh_contexts.append(new_ctx)
        return new_ctx

    fake_bundle = MagicMock()
    fake_bundle.browser = MagicMock()
    fake_bundle.browser.new_context = AsyncMock(side_effect=_fake_new_context)
    fake_bundle.close = AsyncMock()

    async def _fake_setup(base_url: str) -> Any:
        return fake_bundle

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._launch_example_app",
            new=AsyncMock(return_value=fake_handle),
        ),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._stop_example_app"),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._setup_playwright",
            new=_fake_setup,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._build_engine",
            new=AsyncMock(return_value=fake_engine),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._login_as_persona",
            new=AsyncMock(),
        ) as mock_login,
    ):
        outcome = await run_fitness_strategy(
            example_app="support_tickets",
            project_root=tmp_path,
            personas=["admin", "editor", "viewer"],
        )

    # Three fresh contexts were created (one per named persona)
    assert len(fresh_contexts) == 3
    # Each context had close() awaited
    for ctx in fresh_contexts:
        ctx.close.assert_awaited_once()
    # _login_as_persona called three times, one per persona
    assert mock_login.await_count == 3
    # Outcome summary contains all three persona IDs
    assert "admin" in outcome.summary
    assert "editor" in outcome.summary
    assert "viewer" in outcome.summary


@pytest.mark.asyncio
async def test_run_fitness_strategy_single_anonymous_run_backwards_compat(
    tmp_path: Path,
) -> None:
    """personas=None runs a single anonymous cycle using the original bundle context."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )

    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")

    fake_engine = MagicMock()
    fake_engine.run = AsyncMock(
        return_value=MagicMock(
            findings=[],
            profile=MagicMock(degraded=False),
            independence_jaccard=0.0,
            run_metadata={"run_id": "r1"},
        )
    )

    fake_bundle = MagicMock()
    fake_bundle.browser = MagicMock()
    fake_bundle.browser.new_context = AsyncMock()
    fake_bundle.close = AsyncMock()

    async def _fake_setup(base_url: str) -> Any:
        return fake_bundle

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._launch_example_app",
            new=AsyncMock(return_value=fake_handle),
        ),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._stop_example_app"),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._setup_playwright",
            new=_fake_setup,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._build_engine",
            new=AsyncMock(return_value=fake_engine),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._login_as_persona",
            new=AsyncMock(),
        ) as mock_login,
    ):
        outcome = await run_fitness_strategy(
            example_app="support_tickets",
            project_root=tmp_path,
            personas=None,
        )

    # No fresh context (browser.new_context never called)
    fake_bundle.browser.new_context.assert_not_awaited()
    # No login (personas=None means anonymous)
    mock_login.assert_not_awaited()
    # Outcome summary is single-persona format (no bracketed list)
    assert "[" not in outcome.summary
    assert "r1" in outcome.summary


@pytest.mark.asyncio
async def test_run_fitness_strategy_continues_on_persona_failure(tmp_path: Path) -> None:
    """One persona's engine failure produces BLOCKED outcome; other personas still run."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )

    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")

    # Two-engine sequence: first raises, second returns a happy result
    happy_result = MagicMock(
        findings=[],
        profile=MagicMock(degraded=False),
        independence_jaccard=0.0,
        run_metadata={"run_id": "r_happy"},
    )
    raising_engine = MagicMock()
    raising_engine.run = AsyncMock(side_effect=RuntimeError("boom"))
    happy_engine = MagicMock()
    happy_engine.run = AsyncMock(return_value=happy_result)

    fake_bundle = MagicMock()
    fake_bundle.browser = MagicMock()
    fake_bundle.browser.new_context = AsyncMock(
        side_effect=lambda **kw: MagicMock(
            new_page=AsyncMock(return_value=MagicMock(url="http://localhost:3000/")),
            close=AsyncMock(),
        )
    )
    fake_bundle.close = AsyncMock()

    async def _fake_setup(base_url: str) -> Any:
        return fake_bundle

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._launch_example_app",
            new=AsyncMock(return_value=fake_handle),
        ),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._stop_example_app"),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._setup_playwright",
            new=_fake_setup,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._build_engine",
            new=AsyncMock(side_effect=[raising_engine, happy_engine]),
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._login_as_persona",
            new=AsyncMock(),
        ),
    ):
        outcome = await run_fitness_strategy(
            example_app="support_tickets",
            project_root=tmp_path,
            personas=["failing", "happy"],
        )

    # Both engines were asked to run
    raising_engine.run.assert_awaited_once()
    happy_engine.run.assert_awaited_once()
    # Outcome has both personas in summary
    assert "failing" in outcome.summary
    assert "happy" in outcome.summary
    # degraded is True because one failed
    assert outcome.degraded is True


@pytest.mark.asyncio
async def test_run_fitness_strategy_closes_bundle_on_engine_construction_failure(
    tmp_path: Path,
) -> None:
    """If _build_engine raises (e.g. DATABASE_URL unset), bundle is still torn down."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )

    fake_handle = MagicMock(site_url="http://localhost:3000", api_url="http://localhost:8000")

    fake_bundle = MagicMock()
    fake_bundle.browser = MagicMock()
    fake_bundle.close = AsyncMock()

    async def _fake_setup(base_url: str) -> Any:
        return fake_bundle

    with (
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._launch_example_app",
            new=AsyncMock(return_value=fake_handle),
        ),
        patch("dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._stop_example_app"),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._setup_playwright",
            new=_fake_setup,
        ),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy._build_engine",
            new=AsyncMock(side_effect=RuntimeError("DATABASE_URL env var must be set")),
        ),
    ):
        outcome = await run_fitness_strategy(
            example_app="support_tickets",
            project_root=tmp_path,
            personas=None,
        )

    # Bundle was closed even though _build_engine raised
    fake_bundle.close.assert_awaited_once()
    # The single BLOCKED persona outcome was recorded
    assert outcome.findings_count == 0
    assert outcome.degraded is True


@pytest.mark.asyncio
async def test_aggregate_outcomes_single_persona_format() -> None:
    """_aggregate_outcomes produces the single-persona v1.0.2 summary format."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import _aggregate_outcomes

    single_result = MagicMock(
        findings=[],
        profile=MagicMock(degraded=False),
        independence_jaccard=0.42,
        run_metadata={"run_id": "r1"},
    )

    outcome = _aggregate_outcomes([(None, single_result)])

    assert outcome.strategy == "FITNESS"
    assert "r1" in outcome.summary
    assert "independence=0.420" in outcome.summary
    # single-persona should NOT wrap in brackets
    assert "[" not in outcome.summary
    assert outcome.degraded is False
    assert outcome.findings_count == 0


@pytest.mark.asyncio
async def test_aggregate_outcomes_multi_persona_format() -> None:
    """_aggregate_outcomes produces the bracketed multi-persona summary format."""
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import _aggregate_outcomes

    admin_result = MagicMock(
        findings=[1, 2],  # 2 findings
        profile=MagicMock(degraded=False),
        independence_jaccard=0.3,
        run_metadata={"run_id": "r_admin"},
    )
    editor_result = MagicMock(
        findings=[1],  # 1 finding
        profile=MagicMock(degraded=True),
        independence_jaccard=0.8,
        run_metadata={"run_id": "r_editor"},
    )

    outcome = _aggregate_outcomes(
        [
            ("admin", admin_result),
            ("editor", editor_result),
        ]
    )

    # Multi-persona summary is bracketed, contains both run IDs
    assert "[" in outcome.summary
    assert "admin" in outcome.summary
    assert "editor" in outcome.summary
    # Findings sum
    assert outcome.findings_count == 3
    # degraded OR-reduced
    assert outcome.degraded is True


@pytest.mark.asyncio
async def test_aggregate_outcomes_handles_blocked_result() -> None:
    """_aggregate_outcomes works with _BlockedRunResult stand-ins (not just MagicMock).

    Locks in the duck-typed contract between _BlockedRunResult and the
    aggregator: if a future change renames a FitnessRunResult field, the
    stand-in must keep up or this test catches the drift.
    """
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        _aggregate_outcomes,
        _BlockedRunResult,
    )

    outcome = _aggregate_outcomes(
        [
            ("admin", _BlockedRunResult(error="boom")),
        ]
    )

    # Single-persona format (1 outcome) — no brackets in summary
    assert outcome.degraded is True
    assert outcome.findings_count == 0
    assert "blocked" in outcome.summary  # _BlockedRunResult's run_id is "blocked"
