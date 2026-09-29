"""Prepare blind, same-viewport screen pairs and route reviews for adjudication.

This utility copies PNGs into an opaque review pack. It does not judge images
or call a model; agent reviewers read the pack using their existing vision.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import struct
from pathlib import Path
from typing import Any

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(path: Path) -> tuple[int, int]:
    """Read dimensions from a PNG header without an image dependency."""
    with path.open("rb") as image:
        header = image.read(24)
    if len(header) != 24 or not header.startswith(PNG_SIGNATURE) or header[12:16] != b"IHDR":
        raise ValueError(f"Expected a PNG screenshot: {path}")
    return struct.unpack(">II", header[16:24])


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def prepare(input_path: Path, review_dir: Path, mapping_path: Path, *, seed: int) -> Path:
    """Make anonymous A/B copies; keep variant labels in a separate file."""
    review_dir = review_dir.resolve()
    mapping_path = mapping_path.resolve()
    if mapping_path == review_dir or review_dir in mapping_path.parents:
        raise ValueError("Private mapping must be outside the reviewer directory")
    if review_dir.exists() and any(review_dir.iterdir()):
        raise ValueError("Reviewer directory must be empty")

    cases = _read_json(input_path)
    if not isinstance(cases, list) or not cases:
        raise ValueError("Input must be a nonempty JSON list of cases")
    randomizer = random.Random(seed)
    public: list[dict[str, Any]] = []
    private: list[dict[str, Any]] = []
    seen: set[str] = set()
    copies: list[tuple[Path, Path]] = []
    for index, case in enumerate(cases, 1):
        if not isinstance(case, dict):
            raise ValueError("Each case must be an object")
        case_id = case.get("id")
        screens = case.get("screens")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("Case ids must be unique nonempty strings")
        seen.add(case_id)
        if not isinstance(screens, dict) or len(screens) != 2:
            raise ValueError(f"Case {case_id} needs exactly two variant screenshots")
        for field in ("persona", "job", "state"):
            if not isinstance(case.get(field), str) or not case[field]:
                raise ValueError(f"Case {case_id} needs {field}")

        entries: list[tuple[str, Path]] = []
        sizes: set[tuple[int, int]] = set()
        for variant, raw_path in screens.items():
            if not isinstance(variant, str) or not isinstance(raw_path, str):
                raise ValueError(f"Case {case_id} has invalid screenshot entries")
            path = (input_path.parent / raw_path).resolve()
            sizes.add(png_size(path))
            entries.append((variant, path))
        if len(sizes) != 1:
            raise ValueError(f"Case {case_id} screenshots have different dimensions")
        randomizer.shuffle(entries)
        anonymous_id = f"case-{index:03d}"
        assignments: dict[str, str] = {}
        for label, (variant, path) in zip(("A", "B"), entries, strict=True):
            filename = f"{anonymous_id}-{label}.png"
            copies.append((path, review_dir / filename))
            assignments[label] = variant
        width, height = sizes.pop()
        public.append(
            {
                "case_id": anonymous_id,
                "persona": case["persona"],
                "job": case["job"],
                "state": case["state"],
                "viewport": [width, height],
                "A": f"{anonymous_id}-A.png",
                "B": f"{anonymous_id}-B.png",
            }
        )
        private.append({"case_id": anonymous_id, "source_id": case_id, "variants": assignments})

    review_dir.mkdir(parents=True, exist_ok=True)
    for source, destination in copies:
        shutil.copyfile(source, destination)
    manifest = review_dir / "manifest.json"
    _write_json(manifest, public)
    _write_json(mapping_path, private)
    return manifest


def adjudicate(
    manifest_path: Path, review_paths: list[Path], output_path: Path, *, seed: int
) -> Path:
    """Queue disagreements, ties, and a 10% agreement sample for a human."""
    if len(review_paths) < 2:
        raise ValueError("At least two independent reviews are required")
    cases = _read_json(manifest_path)
    if not isinstance(cases, list) or not cases:
        raise ValueError("Manifest must be a nonempty list")
    case_ids = {case["case_id"] for case in cases}
    reviews: list[dict[str, dict[str, str]]] = []
    for path in review_paths:
        entries = _read_json(path)
        if not isinstance(entries, list):
            raise ValueError(f"Review must be a list: {path}")
        by_id: dict[str, dict[str, str]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"Invalid review entry in {path}")
            case_id = entry.get("case_id")
            winner = entry.get("winner")
            reason = entry.get("reason")
            if (
                not isinstance(case_id, str)
                or case_id not in case_ids
                or case_id in by_id
                or winner not in {"A", "B", "tie"}
            ):
                raise ValueError(f"Invalid case or winner in {path}")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"Missing evidence in {path}")
            by_id[case_id] = {"winner": winner, "reason": reason}
        if set(by_id) != case_ids:
            raise ValueError(f"Review does not cover every case: {path}")
        reviews.append(by_id)

    contested: set[str] = set()
    agreed: list[str] = []
    for case_id in sorted(case_ids):
        votes = {review[case_id]["winner"] for review in reviews}
        if len(votes) == 1 and "tie" not in votes:
            agreed.append(case_id)
        else:
            contested.add(case_id)
    randomizer = random.Random(seed)
    calibration = set(randomizer.sample(agreed, math.ceil(len(agreed) / 10))) if agreed else set()
    queue = []
    for case in cases:
        case_id = case["case_id"]
        if case_id not in contested and case_id not in calibration:
            continue
        queue.append(
            {
                **case,
                "reason_for_human": "disagreement" if case_id in contested else "calibration",
                "agent_reviews": [review[case_id] for review in reviews],
            }
        )
    _write_json(output_path, queue)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("prepare", help="Create blind image copies")
    pack.add_argument("input", type=Path)
    pack.add_argument("review_dir", type=Path)
    pack.add_argument("mapping", type=Path)
    pack.add_argument("--seed", type=int, default=0)
    review = commands.add_parser("adjudicate", help="Select cases for human review")
    review.add_argument("manifest", type=Path)
    review.add_argument("output", type=Path)
    review.add_argument("reviews", nargs="+", type=Path)
    review.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.command == "prepare":
        print(prepare(args.input, args.review_dir, args.mapping, seed=args.seed))
    else:
        print(adjudicate(args.manifest, args.reviews, args.output, seed=args.seed))


if __name__ == "__main__":
    main()
