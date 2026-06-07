"""Pass 1 of the test-suite distillation strategy.

Static classification of every test function in tests/ against the
8-archetype taxonomy from docs/proposals/Suite Distillation Strategy.md.

Output:
- tests/audit/classification.json — list of {test_id, file, archetype, confidence, rationale, metrics}
- tests/audit/taxonomy_report.md — single-page summary of distribution

No test execution. No coverage. Pure AST + import-shape heuristics.
"""

from __future__ import annotations

import ast
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = REPO_ROOT / "tests"
OUT_DIR = REPO_ROOT / "tests" / "audit"


@dataclass
class TestMetrics:
    n_asserts: int = 0
    n_mocks: int = 0  # MagicMock, AsyncMock, patch
    n_fixtures: int = 0
    parametrize_n: int = 0  # number of parametrize cases declared
    has_given: bool = False  # @given(...) — Hypothesis property test
    imports_private: list[str] = field(
        default_factory=list
    )  # underscore-prefixed callables imported
    imports_public: list[str] = field(default_factory=list)
    body_lines: int = 0
    has_snapshot: bool = False
    has_issue_ref: bool = False  # e.g. "#1234" in name/docstring
    assert_shapes: list[str] = field(default_factory=list)  # one-word summary per assert


@dataclass
class TestRecord:
    test_id: str  # file::ClassName::test_name OR file::test_name
    file: str
    line: int
    archetype: str
    confidence: float
    rationale: str
    metrics: TestMetrics


def _walk_test_files() -> list[Path]:
    files: list[Path] = []
    for p in TESTS_ROOT.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        if p.name.startswith("test_") or p.name == "conftest.py":
            files.append(p)
    return sorted(files)


def _classify_assert(node: ast.stmt) -> str:
    """Summarise an assert/assertion-call into a one-word shape."""
    if isinstance(node, ast.Assert):
        t = node.test
        if isinstance(t, ast.Compare):
            op = t.ops[0]
            return type(op).__name__.lower()  # eq/noteq/lt/gt/in/notin/is/isnot
        if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not):
            return "not"
        if isinstance(t, ast.Constant):
            return "constant"
        if isinstance(t, ast.Call):
            f = t.func
            if isinstance(f, ast.Name):
                return f"call_{f.id}"
            if isinstance(f, ast.Attribute):
                return f"call_{f.attr}"
        if isinstance(t, ast.Name):
            return "truthy_name"
        return "expr"
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        f = node.value.func
        if isinstance(f, ast.Attribute):
            name = f.attr
            if name.startswith("assert"):
                return name
    return "other"


def _is_snapshot_assert(node: ast.stmt) -> bool:
    """Detect syrupy snapshot/golden-master assertions."""
    if not isinstance(node, ast.Assert):
        return False
    t = node.test
    if isinstance(t, ast.Compare):
        for cmp in [t.left, *t.comparators]:
            if isinstance(cmp, ast.Name) and cmp.id == "snapshot":
                return True
            if isinstance(cmp, ast.Attribute) and cmp.attr in {"snapshot", "syrupy_snapshot"}:
                return True
    return False


def _count_mocks(node: ast.AST) -> int:
    n = 0
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            name = ""
            if isinstance(f, ast.Name):
                name = f.id
            elif isinstance(f, ast.Attribute):
                name = f.attr
            if name in {"MagicMock", "AsyncMock", "Mock", "patch", "patch.object", "patch_object"}:
                n += 1
    return n


def _parametrize_n(decorators: list[ast.expr]) -> int:
    """Return the number of parametrize cases (length of the values list)."""
    for dec in decorators:
        call = dec
        if not isinstance(call, ast.Call):
            continue
        f = call.func
        attr = ""
        if isinstance(f, ast.Attribute):
            attr = f.attr
        if attr == "parametrize":
            # @pytest.mark.parametrize("foo", [a, b, c])
            if len(call.args) >= 2 and isinstance(call.args[1], ast.List):
                return len(call.args[1].elts)
            return 1  # parametrize but couldn't count
    return 0


def _has_given(decorators: list[ast.expr]) -> bool:
    """True if the test carries a Hypothesis ``@given(...)`` decorator.

    Matches both ``@given(...)`` (``from hypothesis import given``) and
    ``@hypothesis.given(...)`` / ``@st.given`` attribute forms."""
    for dec in decorators:
        call = dec if isinstance(dec, ast.Call) else None
        target = call.func if call is not None else dec
        if isinstance(target, ast.Name) and target.id == "given":
            return True
        if isinstance(target, ast.Attribute) and target.attr == "given":
            return True
    return False


def _has_issue_ref(name: str, docstring: str | None) -> bool:
    text = (docstring or "") + " " + name
    return bool(re.search(r"#\d{3,5}|issue \d+|PR \d+|closes #\d+", text, re.I))


def _gather_imports(tree: ast.AST) -> tuple[list[str], list[str]]:
    """Return (private_imports, public_imports) from src/dazzle*."""
    private = []
    public = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if not mod.startswith(("dazzle", "dazzle_back", "dazzle_ui")):
                continue
            for alias in node.names:
                name = alias.name
                if name.startswith("_") and not name.startswith("__"):
                    private.append(f"{mod}.{name}")
                else:
                    public.append(f"{mod}.{name}")
    return private, public


def _classify(metrics: TestMetrics, name: str, file_path: str) -> tuple[str, float, str]:
    """Apply priority rules to assign archetype + confidence + rationale."""
    # 1. Snapshot — has snapshot assert
    if metrics.has_snapshot:
        return "snapshot", 0.95, "uses syrupy/snapshot fixture"

    # 1b. Property-based — @given (Hypothesis). The strongest "already fuzzable" signal:
    # an input space + an invariant. Ranked above parametric_cluster (a @given test that
    # also carries @parametrize is still fundamentally a property test).
    if metrics.has_given:
        return (
            "property_based",
            0.95,
            "@given (Hypothesis) — input space + invariant; already a fuzz target",
        )

    # 2. Parametric cluster — explicit parametrize (these are GOOD; flag for keep, not collapse)
    if metrics.parametrize_n >= 2:
        return (
            "parametric_cluster",
            0.95,
            f"@pytest.mark.parametrize with {metrics.parametrize_n} cases (already collapsed)",
        )

    # 3. Smoke test — 0 or 1 trivial assertion
    if metrics.n_asserts <= 1:
        if metrics.n_asserts == 0:
            return "smoke", 0.85, "no assertions; runs without raising"
        shape = metrics.assert_shapes[0] if metrics.assert_shapes else ""
        if shape in {"isnot", "is", "constant", "truthy_name", "noteq"}:
            return "smoke", 0.7, f"single trivial assert (shape={shape})"

    # 4. Implementation mirror — imports private callables AND uses heavy mocking
    if len(metrics.imports_private) >= 1 and metrics.n_mocks >= 3:
        return (
            "implementation_mirror",
            0.7,
            f"imports {len(metrics.imports_private)} private callable(s) + {metrics.n_mocks} mocks; "
            f"likely re-encodes implementation",
        )
    if len(metrics.imports_private) >= 2:
        return (
            "implementation_mirror",
            0.55,
            f"imports {len(metrics.imports_private)} private (underscore-prefixed) callables; "
            f"may pin internal shape",
        )

    # 5. Regression pin — name/docstring references issue
    if metrics.has_issue_ref:
        return "regression_pin", 0.9, "references issue/PR number"

    # 6. Belt-and-braces — name appears in multiple test files (computed in second pass)
    # Skip here; assigned in the second pass.

    # 7. Default — contract test (most tests fall here)
    return (
        "contract",
        0.5,
        f"{metrics.n_asserts} assertions; default classification (could be contract or hidden mirror)",
    )


def _process_test_function(
    fn: ast.AST,
    name: str,
    file_path: str,
    line: int,
    private_imports_in_file: list[str],
    public_imports_in_file: list[str],
    class_name: str | None = None,
) -> TestRecord:
    metrics = TestMetrics()
    metrics.imports_public = public_imports_in_file
    if hasattr(fn, "decorator_list"):
        metrics.parametrize_n = _parametrize_n(fn.decorator_list)
        metrics.has_given = _has_given(fn.decorator_list)
    docstring = (
        ast.get_docstring(fn) if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef) else None
    )
    metrics.has_issue_ref = _has_issue_ref(name, docstring)
    # Count private callables actually USED in this test body. File-level
    # import count over-flags every test in a heavily-coupled file as a
    # mirror; what we care about is per-test internal coupling.
    private_names_in_file = {p.rsplit(".", 1)[1] for p in private_imports_in_file}
    private_used_here: set[str] = set()
    if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
        metrics.body_lines = max((getattr(fn, "end_lineno", line) or line) - line, 0)
        metrics.n_mocks = _count_mocks(fn)
        for node in ast.walk(fn):
            if isinstance(node, ast.Assert):
                metrics.n_asserts += 1
                metrics.assert_shapes.append(_classify_assert(node))
                if _is_snapshot_assert(node):
                    metrics.has_snapshot = True
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                f = node.value.func
                if isinstance(f, ast.Attribute) and f.attr.startswith(("assert", "expect")):
                    metrics.n_asserts += 1
                    metrics.assert_shapes.append(_classify_assert(node))
            if isinstance(node, ast.Name) and node.id in private_names_in_file:
                private_used_here.add(node.id)
            elif isinstance(node, ast.Attribute) and node.attr in private_names_in_file:
                private_used_here.add(node.attr)
    metrics.imports_private = sorted(private_used_here)

    archetype, confidence, rationale = _classify(metrics, name, file_path)
    test_id = f"{file_path}::{class_name}::{name}" if class_name else f"{file_path}::{name}"
    return TestRecord(
        test_id=test_id,
        file=file_path,
        line=line,
        archetype=archetype,
        confidence=confidence,
        rationale=rationale,
        metrics=metrics,
    )


def classify_file(path: Path) -> list[TestRecord]:
    rel = path.relative_to(REPO_ROOT).as_posix()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    private_imports, public_imports = _gather_imports(tree)

    records: list[TestRecord] = []
    # Walk only the top-level body — ast.walk would recurse into classes
    # and double-count their methods via the FunctionDef branch.
    for top in tree.body:
        if isinstance(top, ast.ClassDef):
            for sub in top.body:
                if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef) and sub.name.startswith(
                    "test_"
                ):
                    records.append(
                        _process_test_function(
                            sub,
                            sub.name,
                            rel,
                            sub.lineno,
                            private_imports,
                            public_imports,
                            class_name=top.name,
                        )
                    )
        elif isinstance(top, ast.FunctionDef | ast.AsyncFunctionDef):
            if top.name.startswith("test_"):
                records.append(
                    _process_test_function(
                        top,
                        top.name,
                        rel,
                        top.lineno,
                        private_imports,
                        public_imports,
                    )
                )
    return records


def detect_belt_and_braces(records: list[TestRecord]) -> None:
    """Second pass: tests with the same name across unit/integration/e2e dirs."""
    by_name: dict[str, list[TestRecord]] = defaultdict(list)
    for r in records:
        by_name[r.test_id.split("::")[-1]].append(r)
    for _name, group in by_name.items():
        if len(group) < 2:
            continue
        # Look for cross-layer presence
        layers = {r.file.split("/")[1] for r in group if r.file.startswith("tests/")}
        if {"unit", "integration"}.issubset(layers) or {"unit", "e2e"}.issubset(layers):
            for r in group:
                if r.archetype == "contract":  # don't override stronger classifications
                    r.archetype = "belt_and_braces"
                    r.rationale = (
                        f"same test name appears across layers {sorted(layers)} — "
                        f"likely redundant unless layers test genuinely different concerns"
                    )
                    r.confidence = 0.6


def write_outputs(records: list[TestRecord]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    classification_path = OUT_DIR / "classification.json"
    with classification_path.open("w") as f:
        json.dump([asdict(r) for r in records], f, indent=2)

    # Taxonomy report
    by_archetype = Counter(r.archetype for r in records)
    by_archetype_high_conf = Counter(r.archetype for r in records if r.confidence >= 0.8)
    by_file_archetype: dict[str, Counter[str]] = defaultdict(Counter)
    for r in records:
        by_file_archetype[r.file][r.archetype] += 1

    total = len(records)
    lines: list[str] = []
    lines.append(f"# Test Suite Taxonomy — Pass 1 ({total:,} test functions)")
    lines.append("")
    lines.append(
        "Static classification per `docs/proposals/Suite Distillation Strategy.md`. "
        "No execution; AST + import-shape heuristics only. Confidence < 0.8 means the "
        "classifier could be wrong; see rationale field."
    )
    lines.append("")
    lines.append("## Distribution")
    lines.append("")
    lines.append("| Archetype | Count | % | High-confidence count |")
    lines.append("|---|---:|---:|---:|")
    for arch in sorted(by_archetype, key=lambda k: -by_archetype[k]):
        pct = 100 * by_archetype[arch] / total
        lines.append(
            f"| {arch} | {by_archetype[arch]:,} | {pct:.1f}% | {by_archetype_high_conf[arch]:,} |"
        )
    lines.append("")

    lines.append("## Action thresholds")
    lines.append("")
    delete_candidates = sum(by_archetype[k] for k in ("smoke",) if by_archetype[k])
    review_candidates = sum(
        by_archetype[k] for k in ("implementation_mirror", "belt_and_braces") if by_archetype[k]
    )
    keep = sum(
        by_archetype[k]
        for k in ("contract", "regression_pin", "parametric_cluster", "snapshot", "property_based")
        if by_archetype[k]
    )
    lines.append(
        f"- **Definitely keep**: {keep:,} "
        "(contract + regression_pin + parametric + snapshot + property_based)"
    )
    lines.append(
        f"- **Property-based (fuzzable; the target archetype)**: "
        f"{by_archetype.get('property_based', 0):,}"
    )
    lines.append(
        f"- **Review for collapse/rewrite**: {review_candidates:,} (implementation_mirror + belt_and_braces)"
    )
    lines.append(
        f"- **Smoke tests** (canary; keep but never as sole coverage): {delete_candidates:,}"
    )
    lines.append("")

    lines.append("## Top 10 implementation-mirror files")
    lines.append("")
    impl_mirror_per_file = Counter(
        r.file for r in records if r.archetype == "implementation_mirror"
    )
    if impl_mirror_per_file:
        for f, n in impl_mirror_per_file.most_common(10):
            lines.append(f"- `{f}` — {n} likely-mirror tests")
    else:
        lines.append("(none flagged)")
    lines.append("")

    lines.append("## Top 10 smoke-test files")
    lines.append("")
    smoke_per_file = Counter(r.file for r in records if r.archetype == "smoke")
    for f, n in smoke_per_file.most_common(10):
        lines.append(f"- `{f}` — {n} smoke tests")
    lines.append("")

    lines.append("## Notes on the classifier")
    lines.append("")
    lines.append("- **smoke**: 0-1 trivial asserts (`is`, `is not`, `==`, truthy name)")
    lines.append(
        "- **implementation_mirror**: imports private (`_`-prefixed) callables AND ≥3 mocks, "
        "OR imports ≥2 private callables. May contain false positives — review the rationale field."
    )
    lines.append(
        "- **parametric_cluster**: already uses `@pytest.mark.parametrize` ≥2 cases — these are "
        "the **good** shape; included here for visibility, not for action."
    )
    lines.append(
        "- **regression_pin**: name/docstring references an issue or PR number "
        "(`#1234`, `closes #X`, `issue 42`)."
    )
    lines.append(
        "- **belt_and_braces**: same test function name appears in tests/unit/ + tests/integration/ "
        "or tests/unit/ + tests/e2e/. May be intentional (testing different layers) — review."
    )
    lines.append(
        "- **snapshot**: uses syrupy `snapshot` fixture in an assert. One bit of signal each."
    )
    lines.append(
        "- **contract**: default; could be a real contract test OR a hidden mirror that the "
        "static classifier didn't catch. Pass 2 (redundancy clustering) and Pass 4 (contract "
        "extraction) refine this further."
    )

    (OUT_DIR / "taxonomy_report.md").write_text("\n".join(lines))


def main() -> None:
    files = _walk_test_files()
    print(f"Classifying {len(files)} test files...")
    all_records: list[TestRecord] = []
    for f in files:
        all_records.extend(classify_file(f))
    print(f"Classified {len(all_records):,} test functions")
    detect_belt_and_braces(all_records)
    write_outputs(all_records)
    print(f"Wrote {OUT_DIR / 'classification.json'}")
    print(f"Wrote {OUT_DIR / 'taxonomy_report.md'}")


if __name__ == "__main__":
    main()
