import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

IndependenceMechanism = Literal[
    "prompt_only", "prompt_plus_model_family", "prompt_plus_model_and_seed"
]


@dataclass(frozen=True)
class FitnessConfig:
    max_tokens_per_cycle: int = 100_000
    max_wall_time_minutes: int = 10
    independence_threshold_jaccard: float = 0.85
    ledger_ttl_days: int = 30
    transcript_ttl_days: int = 30
    paraphrase_graduation_rounds: int = 3
    independence_mechanism: IndependenceMechanism = "prompt_plus_model_family"


def load_fitness_config(project_root: Path) -> FitnessConfig:
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return FitnessConfig()

    data = tomllib.loads(pyproject.read_text())
    section = data.get("dazzle", {}).get("fitness", {})
    mech = section.get("independence_mechanism", {})
    mechanism = mech.get("primary", "prompt_plus_model_family")

    threshold = float(section.get("independence_threshold_jaccard", 0.85))
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(
            f"[dazzle.fitness].independence_threshold_jaccard must be in "
            f"[0.0, 1.0], got {threshold}"
        )

    return FitnessConfig(
        max_tokens_per_cycle=int(section.get("max_tokens_per_cycle", 100_000)),
        max_wall_time_minutes=int(section.get("max_wall_time_minutes", 10)),
        independence_threshold_jaccard=threshold,
        ledger_ttl_days=int(section.get("ledger_ttl_days", 30)),
        transcript_ttl_days=int(section.get("transcript_ttl_days", 30)),
        paraphrase_graduation_rounds=int(section.get("paraphrase_graduation_rounds", 3)),
        independence_mechanism=mechanism,
    )
