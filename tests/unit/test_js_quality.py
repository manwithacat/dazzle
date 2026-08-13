"""JavaScript quality checks — ESLint structural linting + dist syntax validation."""

import shutil
import subprocess
from pathlib import Path

import pytest

JS_SOURCE_DIRS = [
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "page" / "static" / "js",
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "page" / "runtime" / "static" / "js",
]
DIST_DIR = Path(__file__).resolve().parents[2] / "dist"
_ESLINT_GLOBS = ["src/dazzle/page/**/js/*.js"]
# Cold `npx` may download eslint when node_modules is absent (CI matrix has
# no npm ci). 30s was flaky on py3.14 under xdist load — see main red tip
# run 30444524155 (TimeoutExpired while installing eslint@10). 120s still
# flaked on tip run 31734500898 (py3.14 only; py3.12/13 green) — map-only
# self-audit tip. Prefer local bin; pin version on npx; allow one retry.
_ESLINT_TIMEOUT_S = 300
_ESLINT_NPX_PKG = "eslint@10.1.0"


def _eslint_argv(project_root: Path) -> list[str] | None:
    """Prefer local bin; fall back to pinned npx. None when neither is usable."""
    local = project_root / "node_modules" / ".bin" / "eslint"
    if local.is_file():
        return [str(local), *_ESLINT_GLOBS, "--no-warn-ignored"]
    if shutil.which("npx"):
        # --yes: non-interactive install when package is missing from PATH.
        # Pin major/minor to package.json so cold installs hit a stable cache.
        return ["npx", "--yes", _ESLINT_NPX_PKG, *_ESLINT_GLOBS, "--no-warn-ignored"]
    return None


class TestJsLinting:
    def test_eslint_no_errors(self):
        """Source JS files pass ESLint structural checks."""
        project_root = Path(__file__).resolve().parents[2]
        argv = _eslint_argv(project_root)
        if argv is None:
            pytest.skip("eslint not available (no node_modules/.bin/eslint and no npx)")
        last_err: BaseException | None = None
        for _attempt in range(2):
            try:
                result = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    cwd=project_root,
                    timeout=_ESLINT_TIMEOUT_S,
                )
            except subprocess.TimeoutExpired as exc:
                last_err = exc
                continue
            if result.returncode != 0:
                pytest.fail(f"ESLint found errors:\n{result.stdout}\n{result.stderr}")
            return
        pytest.fail(
            f"ESLint timed out after {_ESLINT_TIMEOUT_S}s x2 "
            f"(cold npx install under load?): {last_err!r}"
        )


class TestDistSyntax:
    @pytest.mark.skipif(not shutil.which("node"), reason="node not available")
    def test_dist_js_files_parse(self):
        """All dist/*.js files are syntactically valid JavaScript."""
        if not DIST_DIR.exists():
            pytest.skip("dist/ directory not found")
        js_files = list(DIST_DIR.glob("*.js"))
        assert js_files, "No .js files in dist/"
        for js_file in js_files:
            result = subprocess.run(
                ["node", "--check", str(js_file)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0, f"{js_file.name} has syntax errors:\n{result.stderr}"
