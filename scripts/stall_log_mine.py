"""Mine Claude Code transcripts for agent-experience confusion hot-zones.

Walks JSONL transcripts in ~/.claude/projects/<project>/ and extracts
five stall signatures per session:

  1. Repeat reads of the same file (stale mental model)
  2. Edit-failure-then-reread loops ("String to replace not found", etc.)
  3. Tool result errors ranked by tool + path
  4. Hot files (read/edited across many sessions = gravitational centers)
  5. Repeated grep/search for the same symbol across attempts

Outputs a single markdown report aggregating signals across the last
N sessions. Usage:

    python scripts/stall_log_mine.py [--days 7] [--out dev_docs/agent-stall-mining-YYYY-MM-DD.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

TRANSCRIPTS_DIR = Path.home() / ".claude" / "projects" / "-Volumes-SSD-Dazzle"

# Tool result error patterns that signal the agent had the wrong model
# of the codebase at that moment.
STALE_MODEL_ERRORS = (
    "File has not been read yet",
    "String to replace not found",
    "old_string targets a region the hook reformatted",
    "File has been modified since read",
    "No such file or directory",
    "Pattern not found",
)


@dataclass
class SessionStats:
    session_id: str
    started: datetime | None = None
    ended: datetime | None = None
    tool_calls: int = 0
    file_reads: Counter[str] = field(default_factory=Counter)
    file_edits: Counter[str] = field(default_factory=Counter)
    bash_commands: list[str] = field(default_factory=list)
    grep_patterns: list[str] = field(default_factory=list)
    errors: list[tuple[str, str, str]] = field(default_factory=list)  # (tool, path, error_excerpt)
    edit_failed_then_reread: list[str] = field(default_factory=list)  # paths

    @property
    def duration_min(self) -> float:
        if self.started and self.ended:
            return (self.ended - self.started).total_seconds() / 60
        return 0.0

    @property
    def repeat_reads(self) -> list[tuple[str, int]]:
        return [(p, c) for p, c in self.file_reads.most_common() if c >= 3]


def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_error_result(content: object) -> tuple[bool, str]:
    """Return (is_error, excerpt). Excerpt is the first stale-model match."""
    text = content if isinstance(content, str) else json.dumps(content)
    for pattern in STALE_MODEL_ERRORS:
        if pattern in text:
            idx = text.index(pattern)
            return True, text[max(0, idx - 20) : idx + len(pattern) + 60].replace("\n", " ")
    return False, ""


def analyse_session(path: Path) -> SessionStats:
    stats = SessionStats(session_id=path.stem)
    pending_tool: dict[str, dict] = {}  # tool_use_id -> {"name", "input"}
    last_failed_edit_path: str | None = None

    with path.open() as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = rec.get("type")
            ts = parse_iso(rec.get("timestamp"))
            if ts:
                stats.started = stats.started or ts
                stats.ended = ts

            if t == "assistant":
                content = rec.get("message", {}).get("content") or []
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    stats.tool_calls += 1
                    name = block.get("name", "")
                    inp = block.get("input", {}) or {}
                    use_id = block.get("id")
                    pending_tool[use_id] = {"name": name, "input": inp}
                    if name == "Read":
                        p = inp.get("file_path", "")
                        if p:
                            stats.file_reads[p] += 1
                            if last_failed_edit_path == p:
                                stats.edit_failed_then_reread.append(p)
                            last_failed_edit_path = None
                    elif name in ("Edit", "Write"):
                        p = inp.get("file_path", "")
                        if p:
                            stats.file_edits[p] += 1
                    elif name == "Bash":
                        cmd = inp.get("command", "")[:200]
                        stats.bash_commands.append(cmd)
                        # Capture greps invoked via Bash — much more common
                        # than the Grep tool in practice. Skip flag-only
                        # matches like "-rn" / "-l".
                        import re

                        for m in re.finditer(
                            r"\bgrep\s+((?:-[a-zA-Z]+\s+)*)(['\"]?)([^'\"\s|;&-][^'\"\s|;&]*)\2",
                            cmd,
                        ):
                            pat = m.group(3)
                            if pat and not pat.startswith("-"):
                                stats.grep_patterns.append(pat[:120])
                    elif name == "Grep":
                        stats.grep_patterns.append(inp.get("pattern", "")[:120])

            elif t == "user":
                content = rec.get("message", {}).get("content") or []
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    use_id = block.get("tool_use_id")
                    use = pending_tool.pop(use_id, None)
                    if not use:
                        continue
                    is_err, excerpt = is_error_result(block.get("content"))
                    if is_err:
                        p = use["input"].get("file_path", "") or use["input"].get("pattern", "")
                        stats.errors.append((use["name"], p, excerpt))
                        if use["name"] == "Edit":
                            last_failed_edit_path = use["input"].get("file_path")

    return stats


def aggregate(sessions: list[SessionStats]) -> dict:
    """Roll up signals across sessions."""
    hot_files: Counter[str] = Counter()
    file_touch_sessions: dict[str, set[str]] = defaultdict(set)
    error_by_tool: Counter[str] = Counter()
    error_by_path: Counter[str] = Counter()
    repeat_read_offenders: Counter[str] = Counter()
    edit_then_reread_offenders: Counter[str] = Counter()
    grep_patterns_repeated_in_session: Counter[str] = Counter()

    for s in sessions:
        for p, c in s.file_reads.items():
            hot_files[p] += c
            file_touch_sessions[p].add(s.session_id)
        for p, c in s.file_edits.items():
            hot_files[p] += c
            file_touch_sessions[p].add(s.session_id)
        for tool, path, _ in s.errors:
            error_by_tool[tool] += 1
            if path:
                error_by_path[path] += 1
        for p, c in s.repeat_reads:
            repeat_read_offenders[p] += c
        for p in s.edit_failed_then_reread:
            edit_then_reread_offenders[p] += 1
        gc = Counter(s.grep_patterns)
        for pat, c in gc.items():
            if c >= 3:
                grep_patterns_repeated_in_session[pat] += c

    # Friction score: weighted sum of confusion signals per file. Heavier
    # weights on edit failures + errors because those are wasted tool
    # calls, not just exploration.
    friction: Counter[str] = Counter()
    all_paths = set(repeat_read_offenders) | set(edit_then_reread_offenders) | set(error_by_path)
    for p in all_paths:
        friction[p] = (
            repeat_read_offenders.get(p, 0)
            + 3 * edit_then_reread_offenders.get(p, 0)
            + 5 * error_by_path.get(p, 0)
        )

    return {
        "n_sessions": len(sessions),
        "total_tool_calls": sum(s.tool_calls for s in sessions),
        "total_errors": sum(len(s.errors) for s in sessions),
        "hot_files": hot_files.most_common(20),
        "session_breadth": {p: len(sids) for p, sids in file_touch_sessions.items()},
        "error_by_tool": error_by_tool.most_common(),
        "error_by_path": error_by_path.most_common(15),
        "repeat_read_offenders": repeat_read_offenders.most_common(15),
        "edit_then_reread_offenders": edit_then_reread_offenders.most_common(15),
        "grep_patterns_repeated": grep_patterns_repeated_in_session.most_common(15),
        "friction": friction.most_common(15),
        "_signals_by_path": {
            p: {
                "repeat_reads": repeat_read_offenders.get(p, 0),
                "edit_failures": edit_then_reread_offenders.get(p, 0),
                "errors": error_by_path.get(p, 0),
            }
            for p in all_paths
        },
    }


def shorten(p: str, root: str = "/Volumes/SSD/Dazzle/") -> str:
    return p.replace(root, "") if isinstance(p, str) else p


def render_report(agg: dict, sessions: list[SessionStats], window_days: int) -> str:
    lines = [
        f"# Agent stall-log mining — {datetime.now().date()}",
        "",
        f"Window: last {window_days} days. {agg['n_sessions']} sessions analysed, "
        f"{agg['total_tool_calls']:,} tool calls, {agg['total_errors']:,} "
        f"stale-model errors ({agg['total_errors'] / max(agg['total_tool_calls'], 1) * 100:.1f}%).",
        "",
        "## 0. Friction-ranked AX targets",
        "",
        "Composite score = `repeat_reads + 3 × edit_failures + 5 × errors`. "
        "Files at the top are where agents lose the most time — they re-read "
        "to model, stale-edit, and produce tool errors. Highest-leverage "
        "AX-investment targets.",
        "",
        "| File | Score | Repeat reads | Edit failures | Errors |",
        "|---|---:|---:|---:|---:|",
    ]
    signals = agg["_signals_by_path"]
    for path, score in agg["friction"]:
        sig = signals.get(path, {})
        lines.append(
            f"| `{shorten(path)}` | {score} | "
            f"{sig.get('repeat_reads', 0)} | "
            f"{sig.get('edit_failures', 0)} | "
            f"{sig.get('errors', 0)} |"
        )

    lines += [
        "",
        "## 1. Hot files (gravitational centers)",
        "",
        "Files read or edited most across the window. High count = often-touched; "
        "high session-breadth = relevant to many independent tasks.",
        "",
        "| File | Touches | Sessions |",
        "|---|---:|---:|",
    ]
    breadth = agg["session_breadth"]
    for path, count in agg["hot_files"]:
        lines.append(f"| `{shorten(path)}` | {count} | {breadth.get(path, 0)} |")

    lines += [
        "",
        "## 2. Repeat-read offenders (stale-model risk)",
        "",
        "Files read ≥3 times in a single session — the agent's mental model of "
        "the file kept going stale. Often signals the file is too large, has "
        "non-obvious internal structure, or its public API isn't summarised "
        "near the top.",
        "",
        "| File | Total repeat reads |",
        "|---|---:|",
    ]
    for path, count in agg["repeat_read_offenders"]:
        lines.append(f"| `{shorten(path)}` | {count} |")

    lines += [
        "",
        "## 3. Edit-then-immediate-reread (cache desync)",
        "",
        "An Edit failed, agent then re-Read the same file. Each entry is one "
        "instance. High-count files are where the on-disk state and the "
        "agent's last-read state diverge (often because a formatter or hook "
        "rewrote the file). The PostToolUse:Edit reformat warning in the "
        "harness mitigates this but doesn't eliminate it.",
        "",
        "| File | Edit→reread loops |",
        "|---|---:|",
    ]
    for path, count in agg["edit_then_reread_offenders"]:
        lines.append(f"| `{shorten(path)}` | {count} |")

    lines += [
        "",
        "## 4. Errors by tool + offending paths",
        "",
        "| Tool | Errors |",
        "|---|---:|",
    ]
    for tool, count in agg["error_by_tool"]:
        lines.append(f"| `{tool}` | {count} |")

    lines += [
        "",
        "Top paths producing tool errors:",
        "",
        "| Path / pattern | Errors |",
        "|---|---:|",
    ]
    for path, count in agg["error_by_path"]:
        lines.append(f"| `{shorten(path)}` | {count} |")

    lines += [
        "",
        "## 5. Repeated grep patterns within a session",
        "",
        "Same grep pattern run ≥3 times in one session — the agent kept "
        "looking for the same symbol with different paths. Signals "
        "discoverability friction: the agent doesn't know where things live.",
        "",
        "| Pattern | Total |",
        "|---|---:|",
    ]
    for pat, count in agg["grep_patterns_repeated"]:
        lines.append(f"| `{pat}` | {count} |")

    lines += [
        "",
        "## Worst sessions by error rate",
        "",
        "| Session | Tool calls | Errors | Error rate | Duration (min) |",
        "|---|---:|---:|---:|---:|",
    ]
    ranked = sorted(
        sessions,
        key=lambda s: len(s.errors) / max(s.tool_calls, 1),
        reverse=True,
    )[:10]
    for s in ranked:
        rate = len(s.errors) / max(s.tool_calls, 1) * 100
        lines.append(
            f"| `{s.session_id[:8]}` | {s.tool_calls} | {len(s.errors)} | {rate:.1f}% | {s.duration_min:.0f} |"
        )

    lines += [
        "",
        "## Reading guide",
        "",
        "- Hot files with low session-breadth are tight feedback loops "
        "(one task touched it many times) — not necessarily a problem.",
        "- Hot files with **high** session-breadth are the codebase's "
        "common-touch surfaces — these benefit most from AX investments "
        "(better module-top docstrings, narrower public API, smaller files).",
        "- Repeat-read offenders that *also* show up in edit-then-reread are "
        "the highest-leverage targets — agents both can't model them in one "
        "pass and routinely stale-edit them.",
        "- Grep patterns repeated across sessions are candidates for "
        "knowledge-graph entries or CLAUDE.md pointers.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=7, help="Window in days (default 7)")
    ap.add_argument(
        "--min-tool-calls",
        type=int,
        default=10,
        help="Skip sessions with fewer tool calls (default 10)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default dev_docs/agent-stall-mining-<date>.md)",
    )
    args = ap.parse_args()

    cutoff = datetime.now(UTC) - timedelta(days=args.days)
    transcripts = sorted(
        p for p in TRANSCRIPTS_DIR.glob("*.jsonl") if p.stat().st_mtime >= cutoff.timestamp()
    )
    print(f"Found {len(transcripts)} transcript(s) in the last {args.days} days", file=sys.stderr)

    sessions: list[SessionStats] = []
    for p in transcripts:
        try:
            stats = analyse_session(p)
        except Exception as e:
            print(f"  skip {p.name}: {e}", file=sys.stderr)
            continue
        if stats.tool_calls < args.min_tool_calls:
            continue
        sessions.append(stats)
        print(
            f"  {p.stem[:8]}  tool_calls={stats.tool_calls:>4}  errors={len(stats.errors):>3}  "
            f"reads={sum(stats.file_reads.values()):>3}",
            file=sys.stderr,
        )

    if not sessions:
        print("No sessions with enough tool calls — bailing.", file=sys.stderr)
        return 1

    agg = aggregate(sessions)
    report = render_report(agg, sessions, args.days)
    out = args.out or Path("dev_docs") / f"agent-stall-mining-{datetime.now().date()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"\nWrote {out} ({len(report):,} bytes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
