"""Fitness engine orchestrator (v1 task 19).

Composes every fitness building block — budget planner, snapshot ledger,
story walker, spec extractor, adversary, independence guardrail,
cross-check, progress evaluator, extractor, proxy dispatcher, backlog
writer — into a single cycle. Callers construct one per fitness run.

The engine is async because two of its collaborators (``walk_story`` and
``run_proxy_mission``) are async. Everything else — LLM calls, ledger
snapshots, evaluators — is sync.

The LLM is a sync ``_LlmClient`` protocol (matches
``dazzle.llm.LLMAPIClient.complete``); the database is abstracted behind
``SnapshotSource`` so unit tests can pass an in-memory stub.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dazzle.fitness.adversary import synthesize_from_stories
from dazzle.fitness.backlog import upsert_findings
from dazzle.fitness.budget import BudgetController, CycleProfile
from dazzle.fitness.config import FitnessConfig
from dazzle.fitness.cross_check import cross_check_capabilities
from dazzle.fitness.extractor import extract_findings_from_diff
from dazzle.fitness.independence import measure_independence
from dazzle.fitness.ledger import SnapshotSource
from dazzle.fitness.ledger_snapshot import SnapshotLedger
from dazzle.fitness.maturity import read_maturity
from dazzle.fitness.models import Finding
from dazzle.fitness.progress_evaluator import evaluate_progress
from dazzle.fitness.proxy import run_proxy_mission
from dazzle.fitness.spec_extractor import _LlmClient, extract_spec_capabilities
from dazzle.fitness.walker import walk_story


@dataclass
class FitnessRunResult:
    """Return value from one :meth:`FitnessEngine.run` invocation."""

    pass1_run_count: int
    findings: list[Finding]
    profile: CycleProfile
    independence_jaccard: float
    run_metadata: dict[str, Any] = field(default_factory=dict)


class FitnessEngine:
    """One-shot orchestrator for the Agent-Led Fitness Methodology.

    A fresh engine is constructed per cycle. It does not cache state
    between runs; the per-cycle flow is:

      1. plan a ``CycleProfile`` from the available token budget
      2. open a ``SnapshotLedger`` keyed by a fresh run id
      3. Pass 1 — deterministic story walks (always, if budget permits)
      4. Pass 2a — spec extraction + adversary + cross-check + progress
         evaluation + diff extraction into findings
      5. Pass 2b — free-roam behavioural proxy
      6. persist findings to ``dev_docs/fitness-backlog.md``
    """

    def __init__(
        self,
        project_root: Path,
        config: FitnessConfig,
        app_spec: Any,
        spec_md_path: Path,
        agent: Any,
        executor: Any,
        snapshot_source: SnapshotSource,
        llm: _LlmClient,
    ) -> None:
        self._project_root = project_root
        self._config = config
        self._app = app_spec
        self._spec_path = spec_md_path
        self._agent = agent
        self._executor = executor
        self._source = snapshot_source
        self._llm = llm

    async def run(self) -> FitnessRunResult:
        run_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC)
        maturity = read_maturity(self._project_root)

        profile = BudgetController(self._config).plan(
            available_tokens=self._config.max_tokens_per_cycle
        )

        repr_map = self._collect_repr_fields()
        ledger = SnapshotLedger(source=self._source, repr_fields=repr_map)
        ledger.open(run_id)

        # Pass 1 — deterministic story walks.
        pass1_results: list[Any] = []
        if profile.run_pass1:
            for story in getattr(self._app, "stories", []):
                result = await walk_story(story=story, executor=self._executor, ledger=ledger)
                pass1_results.append(result)

        findings: list[Finding] = []
        jaccard = 0.0

        # Pass 2a — spec cross-check + adversary + independence + progress.
        if profile.run_pass2a:
            spec_caps = extract_spec_capabilities(self._spec_path, llm=self._llm)
            story_caps = (
                synthesize_from_stories(getattr(self._app, "stories", []), llm=self._llm)
                if profile.adversary_enabled
                else []
            )
            indep_report = measure_independence(
                spec_caps,
                story_caps,
                threshold=self._config.independence_threshold_jaccard,
            )
            jaccard = indep_report.jaccard
            low_conf = indep_report.degraded or profile.degraded

            findings.extend(
                cross_check_capabilities(
                    spec_capabilities=spec_caps,
                    stories=getattr(self._app, "stories", []),
                    run_id=run_id,
                    now=now,
                )
            )

            # Progress evaluation for lifecycle-declared entities.
            diff = ledger.summarize()
            for entity in getattr(self._app, "entities", []):
                lifecycle = getattr(entity, "lifecycle", None)
                if lifecycle is None:
                    continue
                progress_records = evaluate_progress(
                    lifecycle,
                    diff,
                    entity_state={},  # v1 — empty; v1.1 hydrates from the real DB
                    entity_name=getattr(entity, "name", "unknown"),
                )
                diff = replace(diff, progress=diff.progress + progress_records)

            findings.extend(
                extract_findings_from_diff(
                    diff,
                    run_id=run_id,
                    persona="fitness_proxy",
                    low_confidence=low_conf,
                    now=now,
                )
            )

        # Pass 2b — free-roam behavioural proxy.
        if profile.run_pass2b:
            for persona in getattr(self._app, "personas", [])[:1]:
                await run_proxy_mission(
                    agent=self._agent,
                    persona=persona,
                    intent="exercise the app as this persona would",
                    step_budget=profile.pass2b_step_budget,
                    ledger=ledger,
                )

        ledger.close()

        backlog_path = self._project_root / "dev_docs" / "fitness-backlog.md"
        backlog_path.parent.mkdir(parents=True, exist_ok=True)
        upsert_findings(backlog_path, findings)

        return FitnessRunResult(
            pass1_run_count=len(pass1_results),
            findings=findings,
            profile=profile,
            independence_jaccard=jaccard,
            run_metadata={
                "run_id": run_id,
                "maturity": maturity,
                "cycle_at": now.isoformat(),
            },
        )

    def _collect_repr_fields(self) -> dict[str, list[str]]:
        """Extract ``fitness.repr_fields`` from every entity in the spec."""
        out: dict[str, list[str]] = {}
        for entity in getattr(self._app, "entities", []):
            fitness = getattr(entity, "fitness", None)
            if fitness is not None and getattr(fitness, "repr_fields", None):
                out[entity.name.lower()] = list(fitness.repr_fields)
        return out
