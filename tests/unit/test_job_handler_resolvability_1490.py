"""#1490 — `dazzle validate` statically checks that each job `run: module:fn`
handler module is resolvable (a file under the project root or an importable
installed package), erroring on the "passes validate, ModuleNotFoundError when
the job fires" class.
"""

from pathlib import Path
from types import SimpleNamespace

from dazzle.cli.project import _job_handler_errors


def _job(name: str, run: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, run=run)


def _appspec(*jobs: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(jobs=list(jobs))


def test_missing_project_module_errors(tmp_path: Path) -> None:
    errs = _job_handler_errors(_appspec(_job("j", "app.jobs:notify")), tmp_path)
    assert len(errs) == 1
    assert "app.jobs" in errs[0] and "not found" in errs[0]


def test_present_project_module_ok(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "jobs.py").write_text("def notify(**p):\n    return p\n")
    errs = _job_handler_errors(_appspec(_job("j", "app.jobs:notify")), tmp_path)
    assert errs == []


def test_present_package_module_ok(tmp_path: Path) -> None:
    # module resolvable as app/jobs/__init__.py (package form)
    (tmp_path / "app" / "jobs").mkdir(parents=True)
    (tmp_path / "app" / "jobs" / "__init__.py").write_text("def notify(**p):\n    return p\n")
    errs = _job_handler_errors(_appspec(_job("j", "app.jobs:notify")), tmp_path)
    assert errs == []


def test_installed_package_handler_not_flagged(tmp_path: Path) -> None:
    # an importable installed package (json) must not be flagged even though it's
    # not under the project root — find_spec resolves it.
    errs = _job_handler_errors(_appspec(_job("j", "json:dumps")), tmp_path)
    assert errs == []


def test_dotted_handler_form_resolves_module(tmp_path: Path) -> None:
    # `module.fn` form (no colon): module is the path minus the trailing attr.
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "jobs.py").write_text("def notify(**p):\n    return p\n")
    errs = _job_handler_errors(_appspec(_job("j", "app.jobs.notify")), tmp_path)
    assert errs == []


def test_empty_run_skipped(tmp_path: Path) -> None:
    assert _job_handler_errors(_appspec(_job("j", "")), tmp_path) == []


def test_multiple_missing_each_reported(tmp_path: Path) -> None:
    errs = _job_handler_errors(
        _appspec(_job("a", "app.jobs:x"), _job("b", "app.tasks:y")),
        tmp_path,
    )
    assert len(errs) == 2
