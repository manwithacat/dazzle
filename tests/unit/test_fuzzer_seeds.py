"""Persisting fuzz-campaign failures as regression seeds (#1342 fuzz-leverage #5)."""

from __future__ import annotations

from dazzle.testing.fuzzer.oracle import Classification, FuzzResult
from dazzle.testing.fuzzer.report import write_seed_files


def test_write_seed_files_only_persists_bugs(tmp_path) -> None:
    results = [
        FuzzResult(dsl_input="module ok", classification=Classification.VALID),
        FuzzResult(dsl_input="bad clean", classification=Classification.CLEAN_ERROR),
        FuzzResult(dsl_input="entity X(crash)", classification=Classification.CRASH),
        FuzzResult(dsl_input="loop forever", classification=Classification.HANG),
    ]
    paths = write_seed_files(results, tmp_path)
    # Only CRASH + HANG inputs are persisted (the bugs); VALID/CLEAN_ERROR are not.
    assert len(paths) == 2
    names = sorted(p.name for p in paths)
    assert names[0].startswith("crash-") and names[1].startswith("hang-")
    assert all(p.suffix == ".dsl" for p in paths)
    contents = {p.read_text(encoding="utf-8") for p in paths}
    assert contents == {"entity X(crash)", "loop forever"}


def test_write_seed_files_dedups_identical_inputs(tmp_path) -> None:
    # Same crashing input twice → one seed file (content-hashed name).
    results = [
        FuzzResult(dsl_input="dup crash", classification=Classification.CRASH),
        FuzzResult(dsl_input="dup crash", classification=Classification.CRASH),
    ]
    assert len(write_seed_files(results, tmp_path)) == 1


def test_write_seed_files_empty_when_no_bugs(tmp_path) -> None:
    results = [FuzzResult(dsl_input="ok", classification=Classification.VALID)]
    assert write_seed_files(results, tmp_path) == []
