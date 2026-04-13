from pathlib import Path

import pytest

from dazzle.fitness.config import load_fitness_config


def test_load_config_defaults_when_section_absent(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "demo"\n')

    cfg = load_fitness_config(tmp_path)

    assert cfg.max_tokens_per_cycle == 100_000
    assert cfg.max_wall_time_minutes == 10
    assert cfg.independence_threshold_jaccard == 0.85
    assert cfg.ledger_ttl_days == 30
    assert cfg.transcript_ttl_days == 30
    assert cfg.paraphrase_graduation_rounds == 3
    assert cfg.independence_mechanism == "prompt_plus_model_family"


def test_load_config_honours_overrides(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "demo"\n\n'
        "[dazzle.fitness]\n"
        "max_tokens_per_cycle = 50000\n"
        "independence_threshold_jaccard = 0.75\n"
        '\n[dazzle.fitness.independence_mechanism]\nprimary = "prompt_only"\n'
    )

    cfg = load_fitness_config(tmp_path)

    assert cfg.max_tokens_per_cycle == 50_000
    assert cfg.independence_threshold_jaccard == 0.75
    assert cfg.independence_mechanism == "prompt_only"


def test_load_config_rejects_invalid_threshold(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[dazzle.fitness]\nindependence_threshold_jaccard = 1.5\n")

    with pytest.raises(ValueError, match="threshold"):
        load_fitness_config(tmp_path)
