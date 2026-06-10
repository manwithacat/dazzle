"""#1358: every KB DSL example must parse with the current grammar.

`knowledge(concept/examples)` is the agent's syntax source of truth — bootstrap
explicitly directs agents there instead of example projects. #1350 showed the
KB can teach removed syntax for months; its regex gate only catches the one
shape we knew about. This gate runs every `example`/`dsl` field in
`src/dazzle/mcp/semantics_kb/*.toml` through the real parser.

Mixed-content entries (DSL interleaved with JSON/Python/bash/diagrams) opt out
explicitly with `parse_check = false` in the TOML entry — the marker is the
documentation that a human decided the entry is not pure DSL. No heuristic
skips: an unmarked entry that doesn't parse is a bug in the entry.

Fragments are wrapped in a minimal `module` + `app` preamble before parsing,
mirroring how an agent would embed the snippet in a real app.
"""

import re
import tomllib
from pathlib import Path

import pytest

from dazzle.core.parser import parse_modules

REPO_ROOT = Path(__file__).resolve().parents[2]
KB_DIR = REPO_ROOT / "src" / "dazzle" / "mcp" / "semantics_kb"

PREAMBLE = 'module kbcheck\n\napp kbcheck "KB Check"\n\n'


def _collect_examples() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for toml_path in sorted(KB_DIR.glob("*.toml")):
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        for section in ("concepts", "patterns"):
            for name, entry in data.get(section, {}).items():
                if not isinstance(entry, dict):
                    continue
                if entry.get("parse_check") is False:
                    continue
                snippet = entry.get("example") or entry.get("dsl")
                if not snippet or not isinstance(snippet, str):
                    continue
                cases.append((f"{toml_path.name}:{section}.{name}", snippet))
    return cases


CASES = _collect_examples()


@pytest.mark.parametrize(("case_id", "snippet"), CASES, ids=[c[0] for c in CASES])
def test_kb_example_parses(case_id: str, snippet: str, tmp_path: Path) -> None:
    text = snippet if re.search(r"^module\s", snippet, re.M) else PREAMBLE + snippet
    dsl_file = tmp_path / "snippet.dsl"
    dsl_file.write_text(text, encoding="utf-8")
    try:
        parse_modules([dsl_file])
    except Exception as exc:  # noqa: BLE001 — surface the parser's message verbatim
        pytest.fail(
            f"KB example {case_id} does not parse with the current grammar.\n"
            f"Fix the example, or — only if it deliberately mixes DSL with other "
            f"languages — add `parse_check = false` to the entry.\n\n"
            f"Parser said:\n{exc}\n\nSnippet (with preamble):\n{text}"
        )


def test_gate_has_coverage() -> None:
    # If extraction breaks (key rename, dir move), fail loudly rather than
    # silently parsing nothing.
    assert len(CASES) > 50, f"only {len(CASES)} KB examples collected — extraction broken?"
