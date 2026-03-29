"""JavaScript quality checks — ESLint structural linting + dist syntax validation."""

import shutil
import subprocess
from pathlib import Path

import pytest

JS_SOURCE_DIRS = [
    Path(__file__).resolve().parents[2] / "src" / "dazzle_ui" / "static" / "js",
    Path(__file__).resolve().parents[2] / "src" / "dazzle_ui" / "runtime" / "static" / "js",
]
DIST_DIR = Path(__file__).resolve().parents[2] / "dist"


class TestJsLinting:
    @pytest.mark.skipif(not shutil.which("npx"), reason="npx not available")
    def test_eslint_no_errors(self):
        """Source JS files pass ESLint structural checks."""
        project_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            ["npx", "eslint", "src/dazzle_ui/**/js/*.js", "--no-warn-ignored"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=30,
        )
        if result.returncode != 0:
            pytest.fail(f"ESLint found errors:\n{result.stdout}\n{result.stderr}")


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
