"""Record the source and image bytes used for an HM visual baseline capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
BASELINES = PACKAGE / "tests" / "baselines"
SITE = PACKAGE / "site"


def source_digest() -> str:
    """Hash the gallery assets that determine captured pixels."""
    digest = hashlib.sha256()
    for path in sorted(SITE.rglob("*")):
        if not path.is_file() or path.suffix not in {
            ".html",
            ".css",
            ".js",
            ".svg",
            ".woff2",
            ".pdf",
        }:
            continue
        digest.update(path.relative_to(SITE).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def image_hashes(platform: str) -> dict[str, str]:
    """Hash every snapshot in one platform's capture set."""
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((BASELINES / platform).glob("*.png"))
    }


def manifest(platform: str) -> dict[str, object]:
    return {"source_digest": source_digest(), "images": image_hashes(platform)}


def write_manifest(platform: str) -> Path:
    target = BASELINES / platform / "capture.json"
    target.write_text(json.dumps(manifest(platform), indent=2, sort_keys=True) + "\n")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", default=sys.platform)
    args = parser.parse_args()
    print(write_manifest(args.platform))
