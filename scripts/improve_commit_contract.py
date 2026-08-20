#!/usr/bin/env python3
"""Improve-cycle commit contract + leftover-token Goodhart gate (oral #127).

Two failure modes this script exists to stop:

1. **Unreadable ships.** ``improve: cycle N leftover-honest <param>`` plus an
   empty body (or a body mashed into the subject) made ``git log`` a dialect
   index instead of a clerk-visible record.
2. **Leftover-token Goodhart.** After oral #121 named the clone, the loop
   still needed a machine stop: at most two consecutive leftover-honest token
   stay-puts, and at most three since the last self-audit. The 4th / 3rd is
   a different invent class — or the push is refused.

Usage::

    python scripts/improve_commit_contract.py --message-file MSG [--paths a b]
    python scripts/improve_commit_contract.py --message-file MSG --paths-from-index
    python scripts/improve_commit_contract.py --head
    python scripts/improve_commit_contract.py --status

Exit 0 = contract ok / status printed. Exit 1 = blocked. Exit 2 = usage.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

MAX_SUBJECT_LEN = 110
MAX_CONSECUTIVE_LEFTOVER_TOKEN = 2
MAX_LEFTOVER_TOKEN_SINCE_AUDIT = 3

SUBJECT_RE = re.compile(
    r"^(?P<kind>improve|fix)(?:\([^)]+\))?: cycle (?P<cycle>\d+) "
    r"(?P<lane>\S+)(?P<harness>(?:\s+harness_only)?) — (?P<summary>.+)$"
)
LABEL_RE = re.compile(
    r"^\s*(?:\*\*)?(Before|After|Live|Not)(?:\*\*)?\s*:\s*(.*)$",
    re.IGNORECASE,
)
LEFTOVER_HONEST_RE = re.compile(r"\bleftover-honest\b", re.IGNORECASE)
TRAILER_RE = re.compile(r"^(Co-Authored-By|Signed-off-by|Change-Id):", re.IGNORECASE)

HARNESS_LANES = frozenset(
    {
        "self-audit",
        "capability-sweep",
    }
)
REPAIR_LANES = frozenset({"cimonitor", "codeql", "github-prs", "consumer-issues"})
PRODUCT_ROOTS = ("src/", "examples/", "packages/")
HARNESS_TEST_MARKERS = (
    "test_improve_",
    "test_push_gate",
    "test_preflight_surface",
    "test_ship_surface",
    "test_clone_ratchet",
    "test_docs_drift",
    "test_gate_marker",
)

NA_LIVE = frozenset({"", "n/a", "na", "none", "-", "—"})

REMEDIATION = """
╔══════════════════════════════════════════════════════════════════════╗
║  IMPROVE COMMIT CONTRACT FAILED (oral #127)                          ║
║  Rewrite the message. Do not push a leftover-token clone.            ║
╚══════════════════════════════════════════════════════════════════════╝

Subject (≤110 chars) names the clerk-visible lie, not the HTTP param:

  improve: cycle N {lane} — CSV money export was raw pence, not £12.00
  improve: cycle N {lane} harness_only — leftover-token cadence (oral #121)

Body (required; Co-Authored-By trailer ok) has labeled lines:

  Before: what the clerk / API saw
  After:  what they see now
  Live:   example app + surface   (or n/a when harness_only)
  Not:    closed class this is not (optional)

Leftover-token stay-put (oral #121): at most 2 consecutive product ships
and at most 3 since the last self-audit. Next mutation is a different
invent class. Machine: python scripts/improve_commit_contract.py --status

Do not start the summary with leftover-honest. Do not mash the body into
the subject. Do not ship an empty body.
"""


@dataclass(frozen=True)
class ParsedMessage:
    kind: str
    cycle: str
    lane: str
    harness_only: bool
    summary: str
    subject: str
    body: str
    labels: dict[str, str]


@dataclass
class Cadence:
    consecutive: int = 0
    since_audit: int = 0
    last_audit: str | None = None
    blocked: bool = False
    reason: str = ""


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def is_improve_subject(subject: str) -> bool:
    text = subject.strip()
    if SUBJECT_RE.match(text):
        return True
    return bool(re.search(r"^(improve|fix)(?:\([^)]+\))?: cycle \d+", text))


def _lane_of(subject: str) -> str:
    m = SUBJECT_RE.match(subject.strip())
    if m:
        return m.group("lane")
    bits = subject.strip().split()
    # improve: cycle N lane …
    for i, tok in enumerate(bits):
        if tok.isdigit() and i + 1 < len(bits):
            return bits[i + 1]
    return ""


def is_harness_lane_subject(subject: str) -> bool:
    text = subject.strip()
    if re.search(r"\bharness_only\b", text):
        return True
    return _lane_of(text) in HARNESS_LANES


def is_repair_lane_subject(subject: str) -> bool:
    return _lane_of(subject.strip()) in REPAIR_LANES


def is_self_audit_subject(subject: str) -> bool:
    return _lane_of(subject.strip()) == "self-audit" or bool(re.search(r"\bself-audit\b", subject))


def is_leftover_token_text(subject: str, body: str = "") -> bool:
    """True when this ship *is* leftover-honest token stay-put.

    Historical subjects used leftover-honest as the mutation name.
    New ships still mention leftover-honest in the body when that is the
    class. Mentions of leftover-token as a *refusal* (``Not: leftover-token``)
    do not count — that string is leftover-token, not leftover-honest.
    """
    if is_harness_lane_subject(subject) or is_repair_lane_subject(subject):
        return False
    blob = f"{subject}\n{body}"
    return bool(LEFTOVER_HONEST_RE.search(blob))


def is_product_paths(paths: list[str] | None) -> bool | None:
    if paths is None:
        return None
    for raw in paths:
        p = raw.replace("\\", "/")
        if p.startswith(PRODUCT_ROOTS):
            return True
        if p.startswith("tests/"):
            name = Path(p).name
            if not any(name.startswith(m) for m in HARNESS_TEST_MARKERS):
                return True
    return False


def strip_trailers(body: str) -> str:
    lines = body.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and TRAILER_RE.match(lines[-1].strip()):
        lines.pop()
        while lines and not lines[-1].strip():
            lines.pop()
    return "\n".join(lines).strip()


def parse_message(text: str) -> ParsedMessage | str:
    """Return ParsedMessage or an error string if the envelope is unusable."""
    raw = text.replace("\r\n", "\n").strip()
    if not raw:
        return "commit message is empty"
    subject, _, rest = raw.partition("\n")
    subject = subject.strip()
    m = SUBJECT_RE.match(subject)
    if not m:
        if is_improve_subject(subject):
            return (
                "subject must be "
                "`improve: cycle N {lane} — {clerk-visible lie}` "
                "(optional `harness_only` before the em dash)"
            )
        return "not an improve-cycle subject"
    body = strip_trailers(rest)
    labels: dict[str, str] = {}
    for line in body.splitlines():
        lm = LABEL_RE.match(line)
        if lm:
            labels[lm.group(1).capitalize()] = lm.group(2).strip()
    return ParsedMessage(
        kind=m.group("kind"),
        cycle=m.group("cycle"),
        lane=m.group("lane"),
        harness_only=bool(m.group("harness") and m.group("harness").strip()),
        summary=m.group("summary").strip(),
        subject=subject,
        body=body,
        labels=labels,
    )


def check_message(text: str, paths: list[str] | None = None) -> CheckResult:
    parsed = parse_message(text)
    if isinstance(parsed, str):
        if parsed == "not an improve-cycle subject":
            return CheckResult()
        return CheckResult(errors=[parsed])

    errors: list[str] = []
    if len(parsed.subject) > MAX_SUBJECT_LEN:
        errors.append(
            f"subject is {len(parsed.subject)} chars (max {MAX_SUBJECT_LEN}); "
            "put the rest in Before/After/Live"
        )
    if ". " in parsed.subject or "; " in parsed.subject:
        errors.append(
            "subject contains body sentences; clerk-visible lie only, details in the body"
        )
    summary_l = parsed.summary.lower()
    if summary_l.startswith("leftover-honest"):
        errors.append(
            "subject starts with leftover-honest (a param walk). "
            "Name the clerk-visible lie first; leftover-honest belongs in the body"
        )
    if not parsed.body:
        errors.append("body is empty — required Before: / After: / Live: lines")
    for key in ("Before", "After", "Live"):
        if key not in parsed.labels:
            errors.append(f"body missing `{key}:` line")

    product = is_product_paths(paths)
    harness_required = parsed.lane in HARNESS_LANES or product is False
    if harness_required and not parsed.harness_only:
        errors.append(
            f"harness-only ship must include `harness_only` in the subject (lane={parsed.lane})"
        )
    if parsed.harness_only and product is True:
        errors.append(
            "harness_only subject but the diff touches product paths (src/examples/packages)"
        )

    live = parsed.labels.get("Live", "").strip().lower()
    if parsed.harness_only or parsed.lane in HARNESS_LANES:
        if "Live" in parsed.labels and live not in NA_LIVE and product is True:
            errors.append("Live: names a product surface on a harness_only ship")
    elif "Live" in parsed.labels and live in NA_LIVE:
        errors.append("product ship Live: must name an example app + surface, not n/a")

    return CheckResult(errors=errors)


def cadence_of(
    subjects: list[str],
    *,
    head_body: str = "",
) -> Cadence:
    """``subjects[0]`` is HEAD (newest)."""
    consecutive = 0
    since_audit = 0
    last_audit: str | None = None
    consecutive_open = True
    seen_audit = False

    for i, subject in enumerate(subjects):
        if not is_improve_subject(subject):
            continue
        if is_self_audit_subject(subject):
            last_audit = last_audit or subject
            seen_audit = True
            consecutive_open = False
            continue
        if is_repair_lane_subject(subject):
            # Chrome-gate / ReDoS repair of a leftover ship is not a rotation.
            continue
        if is_harness_lane_subject(subject):
            consecutive_open = False
            continue
        leftover = is_leftover_token_text(subject, head_body if i == 0 else "")
        if consecutive_open:
            if leftover:
                consecutive += 1
            else:
                consecutive_open = False
        if not seen_audit and leftover:
            since_audit += 1

    blocked = False
    reason = ""
    if consecutive > MAX_CONSECUTIVE_LEFTOVER_TOKEN:
        blocked = True
        reason = f"leftover-token consecutive={consecutive} (max {MAX_CONSECUTIVE_LEFTOVER_TOKEN})"
    elif since_audit > MAX_LEFTOVER_TOKEN_SINCE_AUDIT:
        blocked = True
        reason = (
            f"leftover-token since last self-audit={since_audit} "
            f"(max {MAX_LEFTOVER_TOKEN_SINCE_AUDIT})"
        )
    return Cadence(
        consecutive=consecutive,
        since_audit=since_audit,
        last_audit=last_audit,
        blocked=blocked,
        reason=reason,
    )


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def git_head_message(repo: Path = REPO) -> str:
    return _git(repo, "log", "-1", "--format=%B")


def git_head_paths(repo: Path = REPO) -> list[str]:
    out = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def git_index_paths(repo: Path = REPO) -> list[str]:
    out = _git(repo, "diff", "--cached", "--name-only")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def git_recent_subjects(repo: Path = REPO, limit: int = 40) -> list[str]:
    out = _git(repo, "log", f"-{limit}", "--format=%s")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def check_head(repo: Path = REPO) -> CheckResult:
    message = git_head_message(repo)
    parsed = parse_message(message)
    if isinstance(parsed, str) and parsed == "not an improve-cycle subject":
        return CheckResult()
    paths = git_head_paths(repo)
    result = check_message(message, paths)
    subjects = git_recent_subjects(repo)
    body = parsed.body if isinstance(parsed, ParsedMessage) else ""
    cad = cadence_of(subjects, head_body=body)
    if cad.blocked and is_leftover_token_text(
        parsed.subject if isinstance(parsed, ParsedMessage) else message.split("\n", 1)[0],
        body,
    ):
        result.errors.append(cad.reason + " — pick a different invent class (oral #121/#127)")
    return result


def format_status(cad: Cadence) -> str:
    at_cap = (
        cad.blocked
        or cad.consecutive >= MAX_CONSECUTIVE_LEFTOVER_TOKEN
        or cad.since_audit >= MAX_LEFTOVER_TOKEN_SINCE_AUDIT
    )
    cap = "blocked=1" if cad.blocked else "blocked=0"
    nxt = "leftover-token" if at_cap else "-"
    return (
        f"leftover_token_streak={cad.consecutive}/{MAX_CONSECUTIVE_LEFTOVER_TOKEN} "
        f"since_audit={cad.since_audit}/{MAX_LEFTOVER_TOKEN_SINCE_AUDIT} "
        f"{cap} next_must_not={nxt}"
    )


def print_errors(errors: list[str]) -> None:
    print(REMEDIATION, file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--message-file", type=Path, help="Proposed commit message")
    src.add_argument("--head", action="store_true", help="Validate HEAD")
    src.add_argument("--status", action="store_true", help="Print leftover-token cadence")
    parser.add_argument("--paths", nargs="*", default=None, help="Changed paths")
    parser.add_argument(
        "--paths-from-index",
        action="store_true",
        help="Read staged paths (git diff --cached)",
    )
    args = parser.parse_args(argv)

    if args.status:
        cad = cadence_of(git_recent_subjects())
        print(format_status(cad))
        return 0

    if args.head:
        result = check_head()
        if result.ok:
            print("OK improve commit contract")
            return 0
        print_errors(result.errors)
        return 1

    text = args.message_file.read_text(encoding="utf-8")
    paths = list(args.paths) if args.paths else None
    if args.paths_from_index:
        paths = git_index_paths()
    result = check_message(text, paths)
    if paths is not None:
        parsed = parse_message(text)
        if isinstance(parsed, ParsedMessage) and is_leftover_token_text(
            parsed.subject, parsed.body
        ):
            cad = cadence_of(
                [parsed.subject, *git_recent_subjects()],
                head_body=parsed.body,
            )
            if cad.blocked:
                result.errors.append(
                    cad.reason + " — pick a different invent class (oral #121/#127)"
                )
    if result.ok:
        print("OK improve commit contract")
        return 0
    print_errors(result.errors)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
