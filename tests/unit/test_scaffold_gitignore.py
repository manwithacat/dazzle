"""Regression guard for #1190.

`dazzle init` scaffolds a `.gitignore` that blanket-ignores `.dazzle/`. Alembic
migration files are written to `.dazzle/migrations/versions/` — under ADR-0017
those are schema history and MUST be version-controlled. The scaffold template
therefore negates the migrations subtree back in.
"""

from dazzle.core.init_impl.project import _GITIGNORE_TEMPLATE


def test_scaffold_gitignore_tracks_migration_versions() -> None:
    lines = _GITIGNORE_TEMPLATE.splitlines()
    assert ".dazzle/" in lines, "scaffold should still ignore .dazzle/ broadly"
    dazzle_idx = lines.index(".dazzle/")

    # Negations must appear AFTER the broad `.dazzle/` ignore, and the parent
    # dirs must be negated before the file glob so git descends into them.
    expected = [
        "!.dazzle/migrations/",
        "!.dazzle/migrations/versions/",
        "!.dazzle/migrations/versions/*.py",
    ]
    indices = []
    for pattern in expected:
        assert pattern in lines, f"{pattern!r} missing from scaffold .gitignore"
        idx = lines.index(pattern)
        assert idx > dazzle_idx, f"{pattern!r} must come after the `.dazzle/` ignore"
        indices.append(idx)
    assert indices == sorted(indices), "parent-dir negations must precede the *.py glob"
