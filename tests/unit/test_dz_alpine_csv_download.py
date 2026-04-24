"""Source-regression test for window.dz.downloadCsv (#862).

Safari ignores the `<a download>` attribute for same-origin responses
with `Content-Type: text/csv`, rendering the CSV inline and breaking
the workspace-context-preservation UX. The helper in dz-alpine.js
forces a fetch + Blob + click flow that works on all browsers.

This source-grep test pins the contract so future refactors don't
silently break the Safari path. Full behaviour is verified by the
workspace Playwright gates.
"""

from __future__ import annotations

from pathlib import Path

JS_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle_ui"
    / "runtime"
    / "static"
    / "js"
    / "dz-alpine.js"
)


class TestDownloadCsvHelper:
    def test_helper_exists(self) -> None:
        source = JS_PATH.read_text()
        assert "window.dz.downloadCsv" in source

    def test_uses_fetch_and_blob(self) -> None:
        """The fix relies on fetch → Blob rather than <a download>."""
        source = JS_PATH.read_text()
        assert 'await fetch(url, { credentials: "same-origin" })' in source
        assert "await response.blob()" in source
        assert "URL.createObjectURL(blob)" in source

    def test_includes_download_attribute(self) -> None:
        """The synthesised <a> element must set the download attribute."""
        source = JS_PATH.read_text()
        assert "link.download = filename" in source

    def test_revokes_object_url(self) -> None:
        """Memory-leak guard: URL.revokeObjectURL after the click fires."""
        source = JS_PATH.read_text()
        assert "URL.revokeObjectURL(objectUrl)" in source

    def test_appends_format_csv_query(self) -> None:
        """The helper always requests CSV format — the URL either already
        has a query string or gets one."""
        source = JS_PATH.read_text()
        assert 'endpoint + "&format=csv"' in source
        assert 'endpoint + "?format=csv"' in source

    def test_reports_failures_via_toast(self) -> None:
        source = JS_PATH.read_text()
        assert "window.dz.toast(" in source and "CSV export failed" in source
