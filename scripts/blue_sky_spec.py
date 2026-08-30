#!/usr/bin/env python3
"""Extract a Dazzle-agnostic Blue Sky spec from an example app's DSL.

.venv/bin/python scripts/blue_sky_spec.py --list-examples
.venv/bin/python scripts/blue_sky_spec.py --example invoice_ops --list-slices
.venv/bin/python scripts/blue_sky_spec.py --example invoice_ops --slice approver --write
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
OUT = ROOT / "blue_sky" / "specs"

SKIP_FIELDS = frozenset(
    {
        "id",
        "created_at",
        "updated_at",
        "tenant_id",
        "slug",
        "photo_url",
    }
)
SKIP_BLOCKS = frozenset(
    {
        "permit",
        "scope",
        "fitness",
        "audit",
        "index",
        "ux",
        "related",
        "archetype",
        "tenant_host",
        "display_field",
        "intent",
    }
)
CRUD_NOISE = (
    "saved to database",
    "sees confirmation message",
    "has permission to create",
)
FIREWALL = re.compile(
    r"\b(entity|surface|workspace|region|executed_by|dazzle|hx-|tenant_host|"
    r"hyperpart|triple-hop|triple.hop)\b",
    re.I,
)

ENTITY_RE = re.compile(r'^entity (\w+) "([^"]+)":\s*$')
PROCESS_RE = re.compile(r'^process (\w+) "([^"]+)":\s*$')
STORY_RE = re.compile(r'^story (ST-\d+) "([^"]+)":\s*$')
PERSONA_RE = re.compile(r'^persona (\w+) "([^"]+)":\s*$')
FIELD_RE = re.compile(r"^  ([a-z][a-z0-9_]*)\s*:\s*(.+?)(?:\s*=\s*(.+))?$")
TRANS_RE = re.compile(r"^    ([A-Za-z0-9_]+)\s*->\s*([A-Za-z0-9_]+)\s*:?\s*$")
ENUM_RE = re.compile(r"enum\[([^\]]+)\]")
TOP = re.compile(
    r"^(entity |process |surface |workspace |experience |guide |service |"
    r"module |app |story |persona |nav |tenancy:|analytics:)"
)


def example_dir(name: str) -> Path:
    path = EXAMPLES / name
    if not path.is_dir() or not (path / "dsl").is_dir():
        raise SystemExit(f"no example {name!r} with dsl/ under {EXAMPLES}")
    return path


def list_examples() -> list[str]:
    return sorted(
        p.name
        for p in EXAMPLES.iterdir()
        if p.is_dir() and (p / "dsl").is_dir() and not p.name.startswith(".")
    )


def _dsl_blob(ex: Path) -> str:
    parts: list[str] = []
    for path in sorted((ex / "dsl").rglob("*.dsl")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _strip_dsl_noise(type_s: str) -> str:
    t = type_s.strip()
    for token in ("sensitive", "required", "unique", "auto_add", "auto_update"):
        t = re.sub(rf"\s+{token}\b", "", t)
    t = re.sub(r"\s+pii\([^)]*\)", "", t)
    return t.strip()


def parse_entities(text: str) -> dict[str, dict[str, Any]]:
    lines = text.splitlines()
    out: dict[str, dict[str, Any]] = {}
    i = 0
    while i < len(lines):
        m = ENTITY_RE.match(lines[i])
        if not m:
            i += 1
            continue
        name, label = m.group(1), m.group(2)
        i += 1
        fields: list[dict[str, Any]] = []
        transitions: list[dict[str, str]] = []
        invariants: list[str] = []
        in_transitions = False
        skip_depth = 0
        while i < len(lines):
            ln = lines[i]
            if ln.startswith("#") or not ln.strip():
                i += 1
                continue
            if TOP.match(ln) and not ln.startswith(" "):
                break
            if skip_depth:
                if re.match(r"^  \w", ln) and not ln.startswith("    "):
                    skip_depth = 0
                else:
                    i += 1
                    continue
            head = ln.strip().split(":", 1)[0].strip()
            if ln.startswith("  ") and not ln.startswith("    ") and head in SKIP_BLOCKS:
                skip_depth = 1
                in_transitions = False
                i += 1
                continue
            if re.match(r"^  transitions:\s*$", ln):
                in_transitions = True
                i += 1
                continue
            if in_transitions:
                tm = TRANS_RE.match(ln)
                if tm:
                    rec = {"from": tm.group(1), "to": tm.group(2)}
                    if ln.rstrip().endswith(":"):
                        i += 1
                        while i < len(lines) and (
                            lines[i].startswith("      ") or not lines[i].strip()
                        ):
                            g = lines[i].strip()
                            if g.startswith("message:"):
                                rec["message"] = g.split(":", 1)[1].strip().strip('"')
                            i += 1
                        transitions.append(rec)
                        continue
                    transitions.append(rec)
                    i += 1
                    continue
                if re.match(r"^  \w", ln) and not ln.startswith("    "):
                    in_transitions = False
                else:
                    i += 1
                    continue
            if ln.startswith("  invariant:"):
                invariants.append(ln.split(":", 1)[1].strip())
                i += 1
                continue
            fm = FIELD_RE.match(ln)
            if fm and not ln.startswith("    "):
                fname = fm.group(1)
                if fname not in SKIP_FIELDS and fname not in SKIP_BLOCKS:
                    raw = fm.group(2).strip()
                    entry: dict[str, Any] = {"name": fname, "type": _strip_dsl_noise(raw)}
                    if "required" in raw:
                        entry["required"] = True
                    em = ENUM_RE.search(raw)
                    if em:
                        entry["values"] = [v.strip() for v in em.group(1).split(",")]
                    fields.append(entry)
            i += 1
        out[name] = {
            "name": name,
            "label": label,
            "fields": fields,
            "transitions": transitions,
            "invariants": invariants,
        }
    return out


def parse_processes(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        m = PROCESS_RE.match(lines[i])
        if not m:
            i += 1
            continue
        ident, title = m.group(1), m.group(2)
        i += 1
        steps: list[str] = []
        while i < len(lines):
            ln = lines[i]
            if TOP.match(ln) and not ln.startswith(" "):
                break
            hm = re.search(r'title:\s*"([^"]+)"', ln)
            if hm:
                steps.append(hm.group(1))
            i += 1
        out.append({"id": ident, "title": title, "human_steps": steps})
    return out


def parse_stories(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        m = STORY_RE.match(lines[i])
        if not m:
            i += 1
            continue
        sid, title = m.group(1), m.group(2)
        i += 1
        rec: dict[str, Any] = {"id": sid, "title": title, "then": [], "entities": []}
        while i < len(lines):
            ln = lines[i]
            if STORY_RE.match(ln) or (TOP.match(ln) and not ln.startswith(" ")):
                break
            if ln.strip().startswith("persona:"):
                rec["persona"] = ln.split(":", 1)[1].strip()
            elif ln.strip().startswith("entities:"):
                rec["entities"] = re.findall(r"[A-Z][A-Za-z0-9]+", ln)
            elif ln.strip().startswith("- "):
                item = ln.strip()[2:].strip().strip('"')
                rec["then"].append(_humanize(item))
            i += 1
        rec["title"] = _humanize(title)
        out.append(rec)
    return out


def parse_personas(text: str) -> dict[str, dict[str, str]]:
    lines = text.splitlines()
    out: dict[str, dict[str, str]] = {}
    i = 0
    while i < len(lines):
        m = PERSONA_RE.match(lines[i])
        if not m:
            i += 1
            continue
        ident, label = m.group(1), m.group(2)
        i += 1
        desc = ""
        goals = ""
        while i < len(lines):
            ln = lines[i]
            if TOP.match(ln) and not ln.startswith(" "):
                break
            if ln.strip().startswith("description:"):
                desc = ln.split(":", 1)[1].strip().strip('"')
            elif ln.strip().startswith("goals:"):
                raw_goals = ln.split(":", 1)[1].strip().strip('"')
                goals = raw_goals.split('", "')[0].strip().strip('"')
            i += 1
        out[ident] = {"id": ident, "label": label, "description": desc, "goals": goals}
    return out


def _humanize(text: str) -> str:
    t = text
    t = re.sub(r"surface\.\w+", "the desk", t)
    t = re.sub(r"\bon the \w+_desk\b", "at their desk", t)
    t = re.sub(r"\b\w+_desk\b", "desk", t)
    t = re.sub(r"\bworkspace\b", "desk", t, flags=re.I)
    t = re.sub(r"triple-hops?[^.]*", "opens related records", t, flags=re.I)
    t = re.sub(r"\bhub\b", "record", t, flags=re.I)
    t = re.sub(r"\bregion\b", "area", t, flags=re.I)
    t = re.sub(r"\bexecuted_by\b", "", t, flags=re.I)
    t = re.sub(r"\bdazzle\b", "", t, flags=re.I)
    t = re.sub(r"\bpull queue\b", "related work", t, flags=re.I)
    t = t.replace("_", " ")
    t = re.sub(r"\bdesk desk\b", "desk", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" -")
    return t


def _is_crud_noise(story: dict[str, Any]) -> bool:
    title = (story.get("title") or "").lower()
    if "creates a new" in title:
        thens = story.get("then") or []
        if not thens or all(any(n in t.lower() for n in CRUD_NOISE) for t in thens):
            return True
    if "changes " in title and " from " in title:
        return True
    return False


def discover_slices(ex: Path) -> dict[str, dict[str, Any]]:
    blob = _dsl_blob(ex)
    stories = [s for s in parse_stories(blob) if not _is_crud_noise(s)]
    personas = parse_personas(blob)
    by_persona: dict[str, list[dict[str, Any]]] = {}
    for s in stories:
        p = s.get("persona") or "user"
        by_persona.setdefault(p, []).append(s)
    slices: dict[str, dict[str, Any]] = {}
    for pid, slist in by_persona.items():
        meta = personas.get(pid, {"label": pid, "description": pid, "goals": ""})
        ents: list[str] = []
        for s in slist:
            for e in s.get("entities") or []:
                if e not in ents:
                    ents.append(e)
        who = meta["label"].lower()
        article = "an" if who[:1] in "aeiou" else "a"
        question = f"How does {article} {who} get through the work in front of them today?"
        slices[pid] = {
            "id": pid,
            "title": meta.get("goals") or meta["label"],
            "question": question,
            "persona": pid,
            "label": meta["label"],
            "description": meta.get("description") or meta["label"],
            "stories": slist,
            "entities": ents,
        }
    return slices


def extract_slice(ex: Path, slice_id: str) -> dict[str, Any]:
    slices = discover_slices(ex)
    if slice_id not in slices:
        raise SystemExit(f"unknown slice {slice_id!r}; known: {sorted(slices)}")
    spec = slices[slice_id]
    blob = _dsl_blob(ex)
    entities = parse_entities(blob)
    wanted = set(spec["entities"])
    picked = [entities[k] for k in spec["entities"] if k in entities]
    processes = [
        p
        for p in parse_processes(blob)
        if any(e.lower() in (p["id"] + p["title"]).lower() for e in wanted)
    ]
    return {
        "example": ex.name,
        "slice": slice_id,
        "title": spec["title"],
        "question": spec["question"],
        "persona": spec["persona"],
        "label": spec["label"],
        "description": spec["description"],
        "artifacts": picked,
        "procedures": processes,
        "stories": spec["stories"][:20],
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines: list[str] = [
        f"# {data['title']}",
        "",
        "This is a **domain brief**, not a software-framework spec. Implement a",
        "small, beautiful prototype that makes the jobs below feel inevitable.",
        "Invent navigation, language, and visual system. Do **not** clone an",
        "existing product.",
        "",
        f"**The question this prototype must answer:** {data['question']}",
        "",
        "## People",
        "",
        f"- **{data['label']}** — {data['description']}",
        "",
        "## Jobs (what success feels like)",
        "",
    ]
    for s in data["stories"]:
        lines.append(f"- **{s['title']}**")
    lines += [
        "",
        "## Artifacts",
        "",
        "Things in the world. You may group, rename, or hide them — but the",
        "prototype must tell the truth about each lifecycle.",
        "",
    ]
    for art in data["artifacts"]:
        lines.append(f"### {art['label']}")
        req = [f["name"] for f in art["fields"] if f.get("required")]
        if req:
            lines.append("Required facts: " + ", ".join(req[:8]))
        for f in art["fields"]:
            if (
                f.get("values")
                and f["name"]
                in {
                    "status",
                    "client_status",
                    "state",
                }
                or (f.get("values") and len(f.get("values") or []) <= 8)
            ):
                if f.get("values"):
                    lines.append(f"- **{f['name']}**: {', '.join(f['values'])}")
        if art["transitions"]:
            lines.append("Lifecycle:")
            for t in art["transitions"]:
                extra = f" — {t['message']}" if t.get("message") else ""
                lines.append(f"- {t['from']} → {t['to']}{extra}")
        for inv in art["invariants"]:
            lines.append(f"Rule: {inv}")
        lines.append("")
    if data["procedures"]:
        lines += ["## Procedures (human work, not screens)", ""]
        for p in data["procedures"]:
            lines.append(f"**{p['title']}**")
            for s in p.get("human_steps") or []:
                lines.append(f"- {s}")
            lines.append("")
    lines += [
        "## Moments that must exist",
        "",
    ]
    for s in data["stories"][:8]:
        lines.append(f"- {s['title']}")
        for t in (s.get("then") or [])[:3]:
            if FIREWALL.search(t):
                continue
            lines.append(f"  - {t}")
    lines += [
        "",
        "## Constraints (domain, not stack)",
        "",
        "- Fake auth is fine (a button per person in the brief). In-memory seed is fine.",
        "- Prefer one object the person works *through* over five browsers of rows.",
        "- If a concept is missing, invent it and write it in ASSUMPTIONS.md.",
        "",
        "## Out of this slice",
        "",
        "- Live payments, live identity vendors, multi-product ERPs.",
        "- Extra slices you were not given.",
        "",
    ]
    return "\n".join(lines) + "\n"


def render_implementer(data: dict[str, Any], spec_name: str) -> str:
    return f"""# Independent implementer — Blue Sky ({data["example"]}/{data["slice"]})

You have never seen the originating product.

Read **only** `{spec_name}`. Build a small standalone prototype that answers:

> {data["question"]}

## Stack

Anything fast. Suggested: Vite + React + TypeScript, or plain HTML + CSS.
No backend. Seed in memory. Fake login buttons for the people in the brief.

## Deliverables in this directory

| File | Why |
|------|-----|
| Running app (`npm run dev` or equivalent) | Can be walked in a browser |
| `README.md` | How to log in as each person; which jobs work |
| `ASSUMPTIONS.md` | Domain facts you invented that the brief did not state |
| `JOURNEYS.md` | The 3–7 paths a stranger should walk |

## Success

A stranger can complete the primary job without a tour.
If they need more than about three list screens, start over on information architecture.

## Time box

This session. Depth on the slice beats coverage of the universe. Cap: six screens.

## Walls

- Do not use Dazzle, Hyperparts, or any existing templates from a parent repo.
- Do not read files above this directory.
- Do not clone a live portal. Invent.
"""


def _assert_firewall(text: str, path: Path) -> None:
    hits = sorted({m.group(0).lower() for m in FIREWALL.finditer(text)})
    if hits:
        raise SystemExit(f"firewall failed in {path}: {hits}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--example", help="examples/<name>")
    p.add_argument("--slice", help="persona slice id")
    p.add_argument("--list-examples", action="store_true")
    p.add_argument("--list-slices", action="store_true")
    p.add_argument("--write", action="store_true")
    args = p.parse_args(argv)

    if args.list_examples:
        for name in list_examples():
            print(name)
        return 0

    if not args.example:
        p.error("--example is required (or --list-examples)")

    ex = example_dir(args.example)
    slices = discover_slices(ex)
    if args.list_slices:
        for sid, spec in slices.items():
            n = len(spec["stories"])
            print(f"{sid}\t{spec['label']}\t{n} jobs")
        return 0

    if not args.slice:
        p.error("--slice is required (or --list-slices)")

    data = extract_slice(ex, args.slice)
    md = render_markdown(data)
    impl = render_implementer(data, f"{args.slice}.md")
    if args.write:
        dest = OUT / ex.name
        dest.mkdir(parents=True, exist_ok=True)
        spec_path = dest / f"{args.slice}.md"
        impl_path = dest / f"{args.slice}.implementer.md"
        _assert_firewall(md, spec_path)
        spec_path.write_text(md, encoding="utf-8")
        impl_path.write_text(impl, encoding="utf-8")
        print(spec_path.relative_to(ROOT))
        print(impl_path.relative_to(ROOT))
        return 0
    _assert_firewall(md, Path("<stdout>"))
    sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
