"""Pass 2 (coarse) of the test-suite distillation strategy.

Group tests by (file, class, assertion-shape signature) to find clusters
where ≥3 tests assert the same shape against the same target. These are
candidates for `pytest.mark.parametrize` consolidation.

Output:
- tests/audit/redundancy.json — clusters with size ≥ 3
- tests/audit/redundancy_report.md — single-page summary
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "tests" / "audit"

# Path substrings that mark a test's subject as an input-boundary surface — a cluster of
# same-shape example tests over such a surface is a candidate to collapse into ONE property
# test (an input space + an invariant), which is then a fuzz target. (#1342 fuzz leverage.)
# DSL-text surfaces get the existing corpus+mutator kit ("fuzz"); other arbitrary-input
# surfaces get a Hypothesis property ("property"). Everything else stays "parametrise".
_FUZZ_PATH_HINTS = ("parser", "lexer", "grammar", "_dsl", "dsl_", "tokeniz", "expression_lang")
_PROPERTY_PATH_HINTS = (
    "saml",
    "scim",
    "metadata",
    "crypto",
    "jwt",
    "url",
    "validat",
    "sanitiz",
    "duration",
    "scope",
    "secret_rotation",
    "predicate",
    "token",
)


def recommend_form(file: str, assertion_shape: str) -> tuple[str, str]:
    """(recommended_form, rationale) for collapsing a same-shape cluster.

    A path-based hint, not ground truth: it flags clusters whose subject is an
    input-boundary parser/validator so a human/agent can decide whether to collapse them
    into a fuzzable property test rather than a fixed ``@pytest.mark.parametrize`` list.
    """
    low = file.lower()
    if any(h in low for h in _FUZZ_PATH_HINTS):
        return (
            "fuzz",
            "DSL/parser surface — collapse to a property + add a fuzz target (corpus+mutators)",
        )
    if any(h in low for h in _PROPERTY_PATH_HINTS):
        return (
            "property",
            "input-boundary surface — collapse to a Hypothesis property (input space → invariant)",
        )
    return "parametrise", "enumerable cases — collapse to @pytest.mark.parametrize"


def main() -> None:
    records = json.load((OUT_DIR / "classification.json").open())

    # Cluster key: (file, class, assertion_shape_signature)
    # The shape signature is a sorted tuple of the assertion shapes in the test.
    # Two tests with the same file, same class, and same assert-shape sequence
    # are likely doing the same thing with different inputs.
    clusters: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in records:
        if r["archetype"] in ("parametric_cluster", "snapshot"):
            continue  # already collapsed or special-cased
        parts = r["test_id"].split("::")
        if len(parts) == 3:
            cls = parts[1]
        else:
            cls = "(module)"
        shape = tuple(sorted(r["metrics"]["assert_shapes"]))
        if not shape:
            continue  # no asserts — already classified as smoke
        key = (r["file"], cls, str(shape))
        clusters[key].append(r)

    # Filter to clusters of size ≥ 3
    big_clusters = {k: v for k, v in clusters.items() if len(v) >= 3}
    by_size = sorted(big_clusters.items(), key=lambda kv: -len(kv[1]))

    # Write JSON
    cluster_records = []
    for (file, cls, shape), members in by_size:
        form, form_rationale = recommend_form(file, shape)
        cluster_records.append(
            {
                "file": file,
                "class": cls,
                "assertion_shape": shape,
                "size": len(members),
                "members": [m["test_id"].split("::")[-1] for m in members],
                "recommendation": (
                    "parametrise"
                    if len(members) >= 5
                    else "review (could parametrise or be intentional independent cases)"
                ),
                "recommended_form": form,
                "form_rationale": form_rationale,
            }
        )
    (OUT_DIR / "redundancy.json").write_text(json.dumps(cluster_records, indent=2))

    # Compute deduplication potential
    total_in_clusters = sum(len(v) for v in big_clusters.values())
    if_collapsed = len(big_clusters)  # one parametric test per cluster
    saving = total_in_clusters - if_collapsed

    # Top clusters report
    lines: list[str] = []
    lines.append("# Test Redundancy Report — Pass 2 (coarse)")
    lines.append("")
    lines.append(
        "Clusters where ≥3 tests in the same file/class share the same "
        "assertion-shape signature. Strong candidates for "
        "`@pytest.mark.parametrize` consolidation."
    )
    lines.append("")
    lines.append("## Headline numbers")
    lines.append("")
    lines.append(f"- **Clusters of ≥3**: {len(big_clusters):,}")
    lines.append(f"- **Tests inside those clusters**: {total_in_clusters:,}")
    lines.append(
        f"- **Theoretical saving** if every cluster collapsed to one parametrised test: "
        f"**{saving:,} tests** (≈ {100 * saving / 14295:.1f}% of the suite)"
    )
    lines.append("")
    lines.append(
        "Caveats: not every cluster *should* collapse — sometimes independent "
        "test names carry intentional documentation value. The report below is "
        "ranked by size; larger clusters are more likely to genuinely benefit "
        "from consolidation."
    )
    lines.append("")

    # Distribution of cluster sizes
    size_buckets = Counter()
    for v in big_clusters.values():
        n = len(v)
        if n >= 20:
            size_buckets["20+"] += 1
        elif n >= 10:
            size_buckets["10-19"] += 1
        elif n >= 5:
            size_buckets["5-9"] += 1
        else:
            size_buckets["3-4"] += 1
    lines.append("## Cluster size distribution")
    lines.append("")
    lines.append("| Size | Clusters |")
    lines.append("|---|---:|")
    for label in ("20+", "10-19", "5-9", "3-4"):
        lines.append(f"| {label} | {size_buckets.get(label, 0):,} |")
    lines.append("")

    lines.append("## Top 30 largest clusters")
    lines.append("")
    lines.append("| File | Class | Size | Sample test names |")
    lines.append("|---|---|---:|---|")
    for c in cluster_records[:30]:
        sample = ", ".join(c["members"][:3]) + ("…" if len(c["members"]) > 3 else "")
        lines.append(f"| `{c['file']}` | `{c['class']}` | {c['size']} | {sample} |")
    lines.append("")

    # Files with the most cluster pressure
    file_pressure: Counter[str] = Counter()
    for c in cluster_records:
        file_pressure[c["file"]] += c["size"] - 1  # tests that could be saved
    lines.append("## Top 10 files by collapse-saving potential")
    lines.append("")
    lines.append("| File | Tests that could collapse |")
    lines.append("|---|---:|")
    for f, n in file_pressure.most_common(10):
        lines.append(f"| `{f}` | {n} |")
    lines.append("")

    # Fuzz-target worklist: clusters on input-boundary surfaces are candidates to collapse
    # into a property/fuzz test (not just a parametrize list). This is the #1342 lever —
    # turning the redundancy backlog into a ranked list of new fuzz surfaces.
    fuzzable = [c for c in cluster_records if c["recommended_form"] in ("property", "fuzz")]
    fuzzable.sort(key=lambda c: -c["size"])
    lines.append("## Fuzz-target worklist (property/fuzz-candidate clusters)")
    lines.append("")
    lines.append(
        "Clusters whose subject is an input-boundary surface (parser/validator/crypto/…). "
        "Each is a candidate to collapse into ONE property test (input space → invariant) — "
        "which then becomes a fuzz target — rather than a fixed `@pytest.mark.parametrize` "
        "list. Path-based hint; confirm by reading the cluster. (#1342)"
    )
    lines.append("")
    lines.append(f"- **Property/fuzz-candidate clusters**: {len(fuzzable):,}")
    lines.append("")
    lines.append("| File | Class | Size | Form | Why |")
    lines.append("|---|---|---:|---|---|")
    for c in fuzzable[:30]:
        lines.append(
            f"| `{c['file']}` | `{c['class']}` | {c['size']} | {c['recommended_form']} | "
            f"{c['form_rationale']} |"
        )
    lines.append("")

    lines.append("## How to act on this")
    lines.append("")
    lines.append(
        "1. Pick the largest cluster (top of the list above). "
        "Open the file. Read 3 of the cluster's member tests."
    )
    lines.append(
        "2. If they vary only on input data, collapse to one "
        "`@pytest.mark.parametrize` test. Each removed test removes a "
        "name + a fixture setup + a maintenance burden, but no protective "
        "signal (the parametric form runs the same N cases)."
    )
    lines.append(
        "3. If they assert genuinely different things despite shared shape, "
        "tag the cluster as `keep_all` in `redundancy.json` so the next "
        "audit cycle skips it."
    )
    lines.append(
        "4. Re-run `python3 scripts/distill/classify.py` and "
        "`python3 scripts/distill/cluster.py` to confirm the cluster is gone."
    )

    (OUT_DIR / "redundancy_report.md").write_text("\n".join(lines))
    print(f"Wrote {OUT_DIR / 'redundancy.json'} ({len(cluster_records)} clusters)")
    print(f"Wrote {OUT_DIR / 'redundancy_report.md'}")
    print(f"Theoretical collapse saving: {saving:,} tests")


if __name__ == "__main__":
    main()
