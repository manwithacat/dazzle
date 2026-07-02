"""Pass 3: cross-file structural-duplication audit.

Two views the per-file Pass-2 cluster doesn't show:

1. **Cross-file shape clusters** — tests with identical (class-name, assertion-shape)
   that live in different files. Often means two handler/parser/etc. test files
   are testing the same shape on different entities. Candidates for one
   parametric test or for outright deletion of the redundant file.

2. **Implementation-mirror files** — files where the median test body is
   "set up state, call the public function, assert one value." High mocks +
   short body + few imports_private = tests that pin internal call shapes
   rather than behavior. The strategy doc tags these as the lowest-value
   archetype to keep.

3. **Twin-file pairs** — pairs of files whose body-shape multisets overlap
   >70%. Read together, decide if one supersedes the other.

Output: tests/audit/cross_file.json + cross_file_report.md
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "tests" / "audit"


def main() -> None:
    records = json.load((OUT_DIR / "classification.json").open())

    # === View 1: cross-file (class, assertion-shape, public-target) clusters ===
    # The key MUST include what the tests exercise, not just how they assert.
    # Keying on (class, shape) alone made `(module)` + a common assert pattern
    # match hundreds of unrelated files (the #1530 investigation found a
    # "cluster" of 1,067 tests across 346 files) — a signature artifact, not a
    # collapse opportunity. `imports_public` (the deduped dazzle.* callables a
    # test references) is the target discriminator: same shape + same public
    # surface across files = a genuine copy-pasted pattern that one shared
    # parametrised helper could replace. Tests with no attributable public
    # target are skipped (counted below) — an unattributable shape match is
    # not actionable.
    by_shape: dict[tuple[str, str, tuple[str, ...]], list[dict]] = defaultdict(list)
    untargeted = 0
    for r in records:
        if r["archetype"] in ("parametric_cluster", "snapshot"):
            continue
        parts = r["test_id"].split("::")
        cls = parts[1] if len(parts) == 3 else "(module)"
        shape = tuple(sorted(r["metrics"]["assert_shapes"]))
        if not shape:
            continue
        target = tuple(sorted(set(r["metrics"]["imports_public"])))
        if not target:
            untargeted += 1
            continue
        by_shape[(cls, str(shape), target)].append(r)

    cross_file_clusters = []
    for (cls, shape, target), members in by_shape.items():
        files = {m["file"] for m in members}
        if len(files) < 2 or len(members) < 4:
            continue  # only interesting if >=2 files and >=4 tests
        cross_file_clusters.append(
            {
                "class_name": cls,
                "assertion_shape": shape,
                "public_target": list(target),
                "files": sorted(files),
                "size": len(members),
                "samples": [m["test_id"] for m in members[:6]],
            }
        )
    cross_file_clusters.sort(key=lambda c: -c["size"])

    # === View 2: implementation-mirror file detection ===
    by_file: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_file[r["file"]].append(r)

    impl_mirror_candidates = []
    for file, tests in by_file.items():
        if len(tests) < 8:
            continue  # too small to flag
        n = len(tests)
        # heuristics:
        #   - high "implementation_mirror" archetype share
        #   - OR: high mocks per test AND low body lines
        mirror_count = sum(1 for t in tests if t["archetype"] == "implementation_mirror")
        avg_mocks = sum(t["metrics"]["n_mocks"] for t in tests) / n
        avg_body = sum(t["metrics"]["body_lines"] for t in tests) / n
        avg_asserts = sum(t["metrics"]["n_asserts"] for t in tests) / n
        private_imports = sum(len(t["metrics"]["imports_private"]) for t in tests) / n

        mirror_share = mirror_count / n
        is_candidate = (
            mirror_share >= 0.4
            or (avg_mocks >= 2 and avg_body < 25 and avg_asserts <= 3)
            or (private_imports >= 2 and avg_asserts <= 2)
        )
        if is_candidate:
            impl_mirror_candidates.append(
                {
                    "file": file,
                    "tests": n,
                    "mirror_share": round(mirror_share, 2),
                    "avg_mocks": round(avg_mocks, 1),
                    "avg_body_lines": round(avg_body, 1),
                    "avg_asserts": round(avg_asserts, 1),
                    "private_imports_per_test": round(private_imports, 1),
                }
            )
    impl_mirror_candidates.sort(key=lambda c: -c["tests"])

    # === View 3: twin-file pairs (body-shape multiset overlap) ===
    file_signatures: dict[str, Counter] = {}
    for file, tests in by_file.items():
        if len(tests) < 6:
            continue
        sig = Counter()
        for t in tests:
            shape = tuple(sorted(t["metrics"]["assert_shapes"]))
            if shape:
                sig[shape] += 1
        file_signatures[file] = sig

    files = sorted(file_signatures)
    twin_pairs = []
    for i, f1 in enumerate(files):
        s1 = file_signatures[f1]
        n1 = sum(s1.values())
        for f2 in files[i + 1 :]:
            s2 = file_signatures[f2]
            n2 = sum(s2.values())
            if n1 < 6 or n2 < 6:
                continue
            # Jaccard-style overlap on body-shape multiset
            overlap = sum((s1 & s2).values())
            denom = min(n1, n2)
            if denom == 0:
                continue
            ratio = overlap / denom
            if ratio >= 0.7 and overlap >= 6:
                twin_pairs.append(
                    {
                        "file_a": f1,
                        "file_b": f2,
                        "tests_a": n1,
                        "tests_b": n2,
                        "shared_shape_count": overlap,
                        "overlap_ratio": round(ratio, 2),
                    }
                )
    twin_pairs.sort(key=lambda p: -p["shared_shape_count"])

    # === Write outputs ===
    (OUT_DIR / "cross_file.json").write_text(
        json.dumps(
            {
                "cross_file_clusters": cross_file_clusters[:200],
                "impl_mirror_candidates": impl_mirror_candidates,
                "twin_pairs": twin_pairs[:50],
            },
            indent=2,
        )
    )

    lines: list[str] = []
    lines.append("# Test Cross-File Audit — Pass 3")
    lines.append("")
    lines.append("Three structural views the per-file Pass-2 redundancy report doesn't capture.")
    lines.append("")

    lines.append("## View 1 — Cross-file shape clusters")
    lines.append("")
    lines.append(
        "Tests sharing the same `(class_name, assertion_shape, public_target)` "
        "across multiple files — same assert shape AND the same deduped set of "
        "public dazzle callables. A cluster here is a genuinely copy-pasted "
        "pattern that one shared parametrised helper could replace. (Pre-#1530 "
        "this view keyed on shape alone, which matched hundreds of unrelated "
        "files; the target discriminator makes the numbers actionable.)"
    )
    lines.append("")
    lines.append(f"- **Clusters of size ≥4 across ≥2 files**: {len(cross_file_clusters)}")
    total_tests = sum(c["size"] for c in cross_file_clusters)
    lines.append(f"- **Tests inside cross-file clusters**: {total_tests:,}")
    lines.append(
        f"- **Theoretical saving**: ~{total_tests - len(cross_file_clusters):,} "
        "if each cluster collapses to one parametric test"
    )
    lines.append(
        f"- **Skipped (no attributable public target)**: {untargeted:,} tests — "
        "shape matches without a shared target are not actionable"
    )
    lines.append("")
    lines.append("### Top 25 cross-file clusters")
    lines.append("")
    lines.append("| Class | Size | Target | Files | Sample tests |")
    lines.append("|---|---:|---|---|---|")
    for c in cross_file_clusters[:25]:
        files_str = ", ".join(f"`{f.split('/')[-1]}`" for f in c["files"][:3])
        if len(c["files"]) > 3:
            files_str += f" (+{len(c['files']) - 3} more)"
        samples = ", ".join(s.split("::")[-1] for s in c["samples"][:2])
        target_names = [t.rsplit(".", 1)[-1] for t in c["public_target"][:3]]
        lines.append(
            f"| `{c['class_name']}` | {c['size']} | {', '.join(target_names)} | "
            f"{files_str} | {samples}… |"
        )
    lines.append("")

    lines.append("## View 2 — Implementation-mirror file candidates")
    lines.append("")
    lines.append(
        "Files dominated by tests that pin internal call shapes (high mocks, "
        "short body, low public-import diversity). Strategy doc tags these as "
        "the highest-leverage *deletion* targets — replace with one canonical "
        "behavior test per shape."
    )
    lines.append("")
    lines.append(f"- **Files flagged**: {len(impl_mirror_candidates)}")
    total_mirror_tests = sum(c["tests"] for c in impl_mirror_candidates)
    lines.append(f"- **Tests in flagged files**: {total_mirror_tests:,}")
    lines.append("")
    lines.append("### Top 30 candidates (by test count)")
    lines.append("")
    lines.append(
        "| File | Tests | Mirror share | Avg mocks | Avg body | Avg asserts | Priv imports/test |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for c in impl_mirror_candidates[:30]:
        lines.append(
            f"| `{c['file']}` | {c['tests']} | {c['mirror_share']} | "
            f"{c['avg_mocks']} | {c['avg_body_lines']} | {c['avg_asserts']} | "
            f"{c['private_imports_per_test']} |"
        )
    lines.append("")

    lines.append("## View 3 — Twin file pairs (body-shape multiset overlap ≥70%)")
    lines.append("")
    lines.append(
        "Pairs of files whose tests' assertion-shape distributions match. One "
        "may supersede the other; or they're testing the same shape on two "
        "entities (consolidate)."
    )
    lines.append("")
    lines.append(f"- **Twin pairs**: {len(twin_pairs)}")
    lines.append("")
    lines.append("### Top 30 twin pairs")
    lines.append("")
    lines.append("| File A | File B | A | B | Shared | Overlap |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for p in twin_pairs[:30]:
        a = p["file_a"].split("/")[-1]
        b = p["file_b"].split("/")[-1]
        lines.append(
            f"| `{a}` | `{b}` | {p['tests_a']} | {p['tests_b']} | "
            f"{p['shared_shape_count']} | {p['overlap_ratio']} |"
        )
    lines.append("")

    (OUT_DIR / "cross_file_report.md").write_text("\n".join(lines))

    print(f"Wrote {OUT_DIR / 'cross_file.json'}")
    print(f"Wrote {OUT_DIR / 'cross_file_report.md'}")
    print(
        f"Cross-file clusters: {len(cross_file_clusters)} "
        f"({total_tests:,} tests, ~{total_tests - len(cross_file_clusters):,} theoretical saving)"
    )
    print(
        f"Impl-mirror candidates: {len(impl_mirror_candidates)} "
        f"({total_mirror_tests:,} tests in flagged files)"
    )
    print(f"Twin pairs: {len(twin_pairs)}")


if __name__ == "__main__":
    main()
