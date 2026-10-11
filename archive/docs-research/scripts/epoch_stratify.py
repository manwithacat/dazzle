"""Epoch stratification: do agent-production construct biases persist, shed, or
amplify across model generations?

Attribute every .py diff in the repo's history to the model that authored it (via
the Co-Authored-By commit trailer — models overlap in calendar time, so trailer
attribution is required, not dates), count construct INTRODUCTIONS in added lines,
and normalise per 1,000 added .py lines per model generation.

Run: python docs/research/scripts/epoch_stratify.py
Self-contained (stdlib only); derives the repo root from its own location.
"""

# ruff: noqa  -- illustrative research spike script; not framework code
import re
import subprocess
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

# Co-Authored-By substring -> ordered model-generation bucket
BUCKETS = [("Opus 4.5", "4.5"), ("Opus 4.6", "4.6"), ("Opus 4.7", "4.7"), ("Opus 4.8", "4.8")]


def bucket_for(trailer):
    for sub, b in BUCKETS:
        if sub in trailer:
            return b
    return None


CONSTRUCTS = {
    "mock_interact": re.compile(r"\.assert_(?:any_)?call"),  # assert-on-mock proxy
    "broad_except": re.compile(r"except\s*(?:Exception)?\s*:"),  # exceptions-as-control-flow
    "type_ignore": re.compile(r"#\s*type:\s*ignore"),
    "noqa_blanket": re.compile(r"#\s*noqa\s*(?:#|$)"),  # suppress-everything (anti-pattern)
    "noqa_targeted": re.compile(r"#\s*noqa:\s*\w"),  # suppress one rule (disciplined)
    "todo_marker": re.compile(r"#\s*(?:TODO|FIXME|XXX)\b"),
}


def mine():
    stat = defaultdict(lambda: defaultdict(int))
    fmt = "CMT\x01%(trailers:key=Co-Authored-By,valueonly)"
    proc = subprocess.Popen(
        ["git", "log", "-p", "--no-merges", f"--format={fmt}", "--", "*.py"],
        stdout=subprocess.PIPE,
        text=True,
        cwd=str(REPO),
        bufsize=1,
    )
    cur = None
    for line in proc.stdout:
        if line.startswith("CMT\x01"):
            cur = bucket_for(line[4:])
            continue
        if cur is None or not line.startswith("+") or line.startswith("+++"):
            continue
        stat[cur]["added"] += 1
        for name, rx in CONSTRUCTS.items():
            if rx.search(line[1:]):
                stat[cur][name] += 1
    proc.wait()
    return stat


def main():
    stat = mine()
    cols = list(CONSTRUCTS)
    print("Construct introductions per 1,000 added .py lines, by authoring model:\n")
    print(f"{'epoch':<7}{'+klines':>9}" + "".join(f"{c:>15}" for c in cols))
    for sub, b in BUCKETS:
        s = stat[b]
        kl = (s["added"] or 1) / 1000
        print(f"{b:<7}{s['added'] / 1000:>9.1f}" + "".join(f"{s[c] / kl:>15.3f}" for c in cols))


if __name__ == "__main__":
    main()
