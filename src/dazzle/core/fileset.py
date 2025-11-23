from pathlib import Path

from .manifest import ProjectManifest


def discover_dsl_files(root: Path, manifest: ProjectManifest) -> list[Path]:
    files: list[Path] = []
    for rel in manifest.module_paths:
        base = (root / rel).resolve()
        if not base.exists():
            continue
        for p in base.rglob("*.dsl"):
            files.append(p)
    return sorted(set(files))
