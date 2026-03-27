"""DAZZLE DSL Parser Fuzzer.

Three-layer fuzzer for discovering parser error surface gaps:
- Layer 1 (llm): Haiku generates plausible-wrong DSL
- Layer 2 (mutate): Grammar-aware and token-level mutations of valid DSL
- Layer 3 (near-miss): Injection of known near-miss patterns

Usage:
    from dazzle.testing.fuzzer import run_campaign
    results = run_campaign(examples_dir, layers=["mutate"], samples_per_layer=100)
"""

from __future__ import annotations

from pathlib import Path

from dazzle.testing.fuzzer.corpus import load_corpus
from dazzle.testing.fuzzer.mutator import (
    cross_pollinate,
    delete_token,
    duplicate_line,
    inject_near_miss,
    insert_keyword,
    swap_adjacent_tokens,
)
from dazzle.testing.fuzzer.oracle import Classification, FuzzResult, classify
from dazzle.testing.fuzzer.report import generate_report


def run_campaign(
    examples_dir: Path,
    layers: list[str] | None = None,
    samples_per_layer: int = 100,
    timeout_seconds: float = 5.0,
    dry_run: bool = False,
) -> list[FuzzResult]:
    """Run a fuzz campaign against the DSL parser.

    Args:
        examples_dir: Directory containing seed .dsl files.
        layers: Which layers to run: "llm", "mutate", or both. Default: both.
        samples_per_layer: Number of samples per layer.
        timeout_seconds: Parser timeout for classification.
        dry_run: If True, generate inputs but skip classification.

    Returns:
        List of FuzzResult (or unclassified results in dry-run mode).
    """
    if layers is None:
        layers = ["mutate", "llm"]

    corpus = load_corpus(examples_dir)
    if not corpus:
        return []

    generated_inputs: list[str] = []

    # ── Mutation layer ──
    if "mutate" in layers:
        mutators = [
            insert_keyword,
            delete_token,
            swap_adjacent_tokens,
            duplicate_line,
            inject_near_miss,
        ]
        per_mutator = max(1, samples_per_layer // len(mutators))
        for mutator_fn in mutators:
            for seed in range(per_mutator):
                source = corpus[seed % len(corpus)]
                mutated = mutator_fn(source, seed=seed)
                generated_inputs.append(mutated)

        # Also do cross-pollination
        cross_count = max(1, samples_per_layer // 5)
        for seed in range(cross_count):
            source = corpus[seed % len(corpus)]
            donor = corpus[(seed + 1) % len(corpus)]
            mutated = cross_pollinate(source, donor, seed=seed)
            generated_inputs.append(mutated)

    # ── LLM layer ──
    if "llm" in layers:
        from dazzle.testing.fuzzer.generator import generate_samples

        seed_dsl = corpus[0]
        samples = generate_samples(seed_dsl=seed_dsl, count=samples_per_layer)
        generated_inputs.extend(samples)

    # ── Classification ──
    if dry_run:
        return [
            FuzzResult(dsl_input=inp, classification=Classification.VALID)
            for inp in generated_inputs
        ]

    results: list[FuzzResult] = []
    for inp in generated_inputs:
        result = classify(inp, timeout_seconds=timeout_seconds)
        results.append(result)

    return results


__all__ = [
    "run_campaign",
    "generate_report",
    "Classification",
    "FuzzResult",
    "classify",
]
