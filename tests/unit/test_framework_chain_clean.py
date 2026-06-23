"""Chain-cleanliness gate (Task 5, framework-migration-baseline, ADR-0044).

Assert that the framework's alembic ``versions/`` directory is (and stays) the
single squashed baseline at the stable head — no dev-churn re-accumulation.

Design rules:
  1. Exactly ONE revision file exists in ``src/dazzle/http/alembic/versions/``.
  2. That file has ``down_revision = None`` — it is the chain root.
  3. Its ``revision`` matches the stable head id ``0019_process_runtime_tables``.

If a *documented* incremental migration is intentionally added (the rare
destructive-change or between-releases additive that cannot wait for a
re-squash), update ``_ALLOWED_VERSIONS`` below with its id and a one-line
reason.  The allow-list only ever grows when intentional.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Stable head id — the squashed baseline, Task 2 of ADR-0044.
# ---------------------------------------------------------------------------

_STABLE_HEAD = "0019_process_runtime_tables"

# ---------------------------------------------------------------------------
# Allow-list of documented incremental revisions permitted in the framework
# versions directory between re-squash cycles.  Today: exactly the baseline.
# Format: {revision_id: "one-line reason"}.
# ---------------------------------------------------------------------------

_ALLOWED_VERSIONS: dict[str, str] = {
    _STABLE_HEAD: "squashed baseline (chain root, down_revision=None)",
    # Add documented incrementals here with a reason when intentionally adding
    # a framework migration between releases.  Example:
    # "0020_add_foo": "non-destructive additive — pending re-squash at 0.85.0",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fw_versions_dir() -> Path:
    """Return the framework alembic versions directory."""
    try:
        from dazzle import http as dazzle_http

        return (Path(dazzle_http.__file__).resolve().parent / "alembic" / "versions").resolve()
    except (ImportError, AttributeError):
        return (
            Path(__file__).resolve().parents[3] / "src" / "dazzle" / "http" / "alembic" / "versions"
        ).resolve()


def _revision_files(versions_dir: Path) -> list[Path]:
    """Return Python files in versions_dir that declare a revision= assignment."""
    return [p for p in sorted(versions_dir.glob("*.py")) if p.name != "__init__.py"]


def _extract_assignments(path: Path) -> dict[str, object]:
    """Extract top-level string/None module assignments from a Python file via AST."""
    tree = ast.parse(path.read_text())
    result: dict[str, object] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            for target in stmt.targets:
                if not isinstance(target, ast.Name):
                    continue
                name = target.id
                value = stmt.value
                if isinstance(value, ast.Constant):
                    result[name] = value.value
                elif isinstance(value, ast.Tuple) and len(value.elts) == 0:
                    result[name] = ()
        break  # only top-level (module body) — ast.walk visits all; early break via Module
    return result


def _parse_revision_file(path: Path) -> tuple[str, object]:
    """Return (revision, down_revision) parsed from the file.

    Falls back to regex if the AST path misses the assignment (e.g. unusual formatting).
    """
    assignments = _extract_assignments(path)

    _SENTINEL = object()
    rev: str | None = None
    down: object = _SENTINEL

    if "revision" in assignments:
        rev = str(assignments["revision"])
    if "down_revision" in assignments:
        down = assignments["down_revision"]

    # Regex fallback for revision=
    if rev is None:
        m = re.search(r'^revision\s*=\s*["\']([^"\']+)["\']', path.read_text(), re.MULTILINE)
        if m:
            rev = m.group(1)

    # Regex fallback for down_revision= None
    if down is _SENTINEL:
        m2 = re.search(r"^down_revision\s*=\s*(None)", path.read_text(), re.MULTILINE)
        if m2:
            down = None
        else:
            m3 = re.search(
                r'^down_revision\s*=\s*["\']([^"\']+)["\']', path.read_text(), re.MULTILINE
            )
            if m3:
                down = m3.group(1)

    if rev is None:
        pytest.fail(
            f"Could not parse 'revision' from {path.name}. Is it a valid Alembic revision file?"
        )

    return rev, down  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFrameworkChainClean:
    """Framework versions/ directory must stay chain-clean — single squashed baseline."""

    def test_exactly_one_revision_file(self) -> None:
        """There must be exactly 1 revision file in the framework versions/ directory.

        Failure means a framework migration was added without updating
        _ALLOWED_VERSIONS (if intentional) or without squashing (if it was
        supposed to be folded into the baseline).
        """
        versions_dir = _fw_versions_dir()
        assert versions_dir.is_dir(), (
            f"Framework alembic versions directory not found: {versions_dir}\n"
            "Check that dazzle.http.alembic.versions/ exists."
        )

        files = _revision_files(versions_dir)
        if len(files) != len(_ALLOWED_VERSIONS):
            extra = sorted(f.name for f in files if f.stem not in _ALLOWED_VERSIONS)
            missing = sorted(k for k in _ALLOWED_VERSIONS if not any(f.stem == k for f in files))
            detail_parts = []
            if extra:
                detail_parts.append(
                    f"  Unexpected files (add to _ALLOWED_VERSIONS if intentional): {extra}"
                )
            if missing:
                detail_parts.append(
                    f"  Expected but absent (removed without updating _ALLOWED_VERSIONS?): {missing}"
                )
            pytest.fail(
                f"Framework versions/ has {len(files)} revision file(s), "
                f"expected {len(_ALLOWED_VERSIONS)} "
                f"(allowed: {sorted(_ALLOWED_VERSIONS)}).\n" + "\n".join(detail_parts)
            )

    def test_baseline_is_chain_root(self) -> None:
        """The stable baseline must have down_revision=None (it IS the chain root)."""
        versions_dir = _fw_versions_dir()
        files = _revision_files(versions_dir)

        roots = []
        for f in files:
            rev, down = _parse_revision_file(f)
            if down is None:
                roots.append((rev, f.name))

        assert len(roots) >= 1, (
            f"No revision with down_revision=None found in {versions_dir}.\n"
            "The chain-cleanliness gate requires the squashed baseline to be "
            "the chain root (down_revision=None)."
        )
        assert len(roots) == 1, (
            f"Multiple chain roots (down_revision=None) found in {versions_dir}:\n"
            + "\n".join(f"  {rev!r} ({fname})" for rev, fname in roots)
            + "\nOnly the squashed baseline should be a root."
        )

    def test_stable_head_id_present(self) -> None:
        """The stable head revision id must exist and be the chain root."""
        versions_dir = _fw_versions_dir()
        files = _revision_files(versions_dir)

        _MISSING = object()
        found_rev: str | None = None
        found_down: object = _MISSING
        for f in files:
            rev, down = _parse_revision_file(f)
            if rev == _STABLE_HEAD:
                found_rev = rev
                found_down = down
                break

        assert found_rev is not None, (
            f"Stable head revision '{_STABLE_HEAD}' not found in {versions_dir}.\n"
            f"The squashed baseline file must declare revision = {_STABLE_HEAD!r}.\n"
            f"Files present: {[f.name for f in files]}"
        )
        assert found_down is None, (
            f"Revision '{_STABLE_HEAD}' exists but has down_revision={found_down!r} — "
            f"expected None (chain root).\n"
            "The squashed baseline must be the chain root (down_revision=None)."
        )

    def test_no_unlisted_revision_files(self) -> None:
        """Every revision file must be in _ALLOWED_VERSIONS.

        This prevents silent drift: if a migration is added without updating
        the allow-list, this test names the unexpected file.
        """
        versions_dir = _fw_versions_dir()
        files = _revision_files(versions_dir)

        unlisted = []
        for f in files:
            rev, _ = _parse_revision_file(f)
            if rev not in _ALLOWED_VERSIONS:
                unlisted.append(f"  {f.name!r}  (revision={rev!r})")

        assert not unlisted, (
            "Framework versions/ contains revision file(s) not in _ALLOWED_VERSIONS:\n"
            + "\n".join(unlisted)
            + "\n\nIf this is an intentional incremental migration, add its id to "
            "_ALLOWED_VERSIONS in tests/unit/test_framework_chain_clean.py with a one-line reason.\n"
            "If it should have been squashed into the baseline, remove it and "
            "run `dazzle db reframework-baseline` to regenerate the snapshot."
        )

    def test_allowed_versions_all_present(self) -> None:
        """Every entry in _ALLOWED_VERSIONS must correspond to a real revision file.

        Prevents the allow-list from going stale (e.g., after a re-squash that
        removed an incremental migration without updating _ALLOWED_VERSIONS).
        """
        versions_dir = _fw_versions_dir()
        files = _revision_files(versions_dir)

        present_ids = set()
        for f in files:
            rev, _ = _parse_revision_file(f)
            present_ids.add(rev)

        stale = sorted(k for k in _ALLOWED_VERSIONS if k not in present_ids)
        assert not stale, (
            f"_ALLOWED_VERSIONS references revision id(s) with no matching file in {versions_dir}:\n"
            + "\n".join(f"  {k!r}  ({_ALLOWED_VERSIONS[k]})" for k in stale)
            + "\n\nRemove stale entries from _ALLOWED_VERSIONS after a re-squash."
        )
