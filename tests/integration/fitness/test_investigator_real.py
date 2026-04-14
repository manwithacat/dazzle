"""Integration smoke test — real LLM against a fixture cluster.

Gated behind @pytest.mark.e2e. Runs only when the user explicitly opts in
(e.g., `pytest -m e2e`). Costs real tokens. Expected to catch pipeline
regressions (import errors, dataclass incompatibilities, disk I/O failures),
not assert on specific fix content.
"""

import os
import shutil
from pathlib import Path

import pytest

from dazzle.fitness.investigator.proposal import load_proposal
from dazzle.fitness.investigator.runner import run_investigation
from dazzle.fitness.triage import read_queue_file

FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "investigator_smoke"


@pytest.mark.e2e
async def test_investigator_real_llm_pipeline_runs_to_completion(tmp_path: Path) -> None:
    """Run the investigator against a real LLM and verify the pipeline completes.

    This is a smoke test. We assert the pipeline runs end-to-end without
    raising an exception and writes at least one artefact (proposal or
    blocked record). We do NOT assert on specific fix content because the
    LLM is non-deterministic — a "blocked" outcome is a valid completion.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    # Copy the fixture into tmp_path so we don't pollute the real fixture dir
    shutil.copytree(FIXTURE_ROOT, tmp_path / "smoke")
    project_root = tmp_path / "smoke"

    # Load the fixture cluster
    clusters = read_queue_file(project_root / "dev_docs" / "fitness-queue.md")
    assert len(clusters) == 1, f"expected 1 cluster in fixture queue, got {len(clusters)}"
    cluster = clusters[0]

    # Build a real LLM client and attach the run_id the runner Protocol requires.
    from dazzle.llm.api_client import LLMAPIClient

    llm = LLMAPIClient(model="claude-sonnet-4-6", temperature=0.2)
    llm.run_id = "smoke-integration-run"  # type: ignore[attr-defined]

    # run_investigation must not raise — that's the primary smoke assertion.
    result = await run_investigation(
        cluster=cluster,
        dazzle_root=project_root,
        llm_client=llm,
        force=False,
        dry_run=False,
    )

    cluster_id = cluster.cluster_id
    proposals_dir = project_root / ".dazzle" / "fitness-proposals"

    # Primary smoke assertion: _metrics.jsonl is always written on any run
    # (proposed, blocked_stagnation, blocked_step_cap, etc.).  Its existence
    # proves append_metric ran, the directory was created, and the runner
    # reached its terminal bookkeeping phase without raising.
    metrics = proposals_dir / "_metrics.jsonl"
    assert metrics.exists(), (
        "metrics file must exist after any pipeline run — "
        f"proposals_dir exists: {proposals_dir.exists()}"
    )
    lines = [ln for ln in metrics.read_text().strip().split("\n") if ln.strip()]
    assert len(lines) >= 1, "metrics file must contain at least one entry"

    # If the LLM successfully produced a proposal, also validate its shape.
    # A "blocked" or "stagnation" outcome is equally valid for a smoke test —
    # we are checking the pipeline wiring, not LLM quality.
    if result is not None:
        assert result.cluster_id == cluster_id
        assert len(result.fixes) >= 1
        assert 0.0 <= result.overall_confidence <= 1.0
        # Proposal file must exist on disk and round-trip cleanly.
        proposals = list(proposals_dir.glob(f"{cluster_id}-*.md"))
        assert len(proposals) >= 1, "run_investigation returned a Proposal but no file found"
        loaded = load_proposal(proposals[0])
        assert loaded.cluster_id == cluster_id
