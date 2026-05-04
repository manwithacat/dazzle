"""Per-app interactive fuzz runner."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FuzzCheck:
    """One assertion in a fuzz run."""

    name: str
    passed: bool
    detail: str = ""


@dataclass
class FuzzReport:
    """Result of fuzzing one app."""

    project: str
    checks: list[FuzzCheck] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    skipped_reason: str | None = None

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def failures(self) -> list[FuzzCheck]:
        return [c for c in self.checks if not c.passed]


@contextmanager
def _booted_app(project_root: Path, port: int = 3158) -> Iterator[tuple[str, str]]:
    """Boot the app under test on `port`; yield (base_url, test_secret).

    Cleanup tears down the subprocess.
    """
    env = {"DAZZLE_SKIP_INFRA_CHECK": "1"}
    proc = subprocess.Popen(
        ["dazzle", "serve", "--local", "--test-mode"],
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**__import__("os").environ, **env},
    )
    base = f"http://127.0.0.1:{port}"
    runtime_path = project_root / ".dazzle" / "runtime.json"
    deadline = time.time() + 15
    secret = ""
    try:
        while time.time() < deadline:
            if runtime_path.exists():
                try:
                    secret = json.loads(runtime_path.read_text()).get("test_secret", "")
                    if secret:
                        break
                except Exception:
                    pass
            time.sleep(0.2)
        if not secret:
            raise RuntimeError("test_secret not published in runtime.json")
        # Wait until /openapi.json is reachable. Use httpx (existing
        # framework dependency) — avoids the standard-library scanner
        # warning about dynamic URL construction even though the URL
        # is always a fixed loopback string.
        import httpx

        for _ in range(40):
            try:
                with httpx.Client(timeout=0.5) as c:
                    if c.get(f"{base}/openapi.json").status_code == 200:
                        break
            except Exception:
                time.sleep(0.25)
        yield base, secret
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _authenticate(base: str, secret: str, role: str = "admin") -> dict[str, str]:
    """Hit /__test__/authenticate and return the session/csrf cookies."""
    import httpx

    with httpx.Client(timeout=5) as client:
        resp = client.post(
            f"{base}/__test__/authenticate",
            json={"username": role, "role": role},
            headers={"X-Test-Secret": secret},
        )
        resp.raise_for_status()
        # httpx exposes cookies as a dict-like; convert to plain {name: value}.
        return dict(resp.cookies.items())


def fuzz_richtext(page: Any, host_index: int = 0) -> list[FuzzCheck]:
    """Drive one dz-richtext editor through known-tricky sequences.

    Each check records a name + pass/fail + short detail string.
    Findings (cycle 1 of this module): selection that spans a whole
    block produces invalid <strong><p>...</p></strong> nesting (#1000).
    """
    checks: list[FuzzCheck] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append(FuzzCheck(name=name, passed=ok, detail=detail))

    host = page.locator('[data-dz-widget="richtext"]').nth(host_index)
    if host.count() == 0:
        return checks
    editor = host.locator("[data-dz-editor]")
    hidden = host.locator("input[type=hidden]")

    # 1. Type → hidden sync.
    editor.click()
    page.keyboard.type("hello world")
    page.wait_for_timeout(100)
    hv = hidden.input_value()
    add("type → hidden sync", "hello world" in hv, hv)

    # 2. Bold via shortcut.
    editor.evaluate(
        "el => { const r = document.createRange(); r.selectNodeContents(el); "
        "const s = window.getSelection(); s.removeAllRanges(); s.addRange(r); }"
    )
    page.keyboard.press("Control+b")
    page.wait_for_timeout(100)
    hv = hidden.input_value()
    add("Ctrl+B inserts <strong>", "<strong>" in hv, hv)
    # #1000 — inline tags must not wrap block tags.
    add(
        "Ctrl+B does NOT wrap <p> in <strong> (#1000)",
        "<strong><p>" not in hv and "<strong>\n<p>" not in hv,
        hv,
    )

    # 3. Paste javascript: link → href stripped.
    page.evaluate(
        """() => {
            const ed = document.querySelector('[data-dz-widget=\\"richtext\\"]')
                .querySelector('[data-dz-editor]');
            ed.focus();
            const dt = new DataTransfer();
            dt.setData('text/html', '<a href=\\"javascript:alert(1)\\">click</a>');
            ed.dispatchEvent(new ClipboardEvent('paste', {
                clipboardData: dt, bubbles: true, cancelable: true
            }));
        }"""
    )
    page.wait_for_timeout(100)
    hv = hidden.input_value()
    add("javascript: href stripped on paste", "javascript" not in hv, hv)

    # 4. Paste <script> → no execution, tag stripped.
    page.evaluate(
        """() => {
            const ed = document.querySelector('[data-dz-widget=\\"richtext\\"]')
                .querySelector('[data-dz-editor]');
            ed.focus();
            const dt = new DataTransfer();
            dt.setData('text/html',
                '<p>before</p><script>window.__pwn_richtext = 1<' + '/script><p>after</p>');
            ed.dispatchEvent(new ClipboardEvent('paste', {
                clipboardData: dt, bubbles: true, cancelable: true
            }));
        }"""
    )
    page.wait_for_timeout(100)
    pwn = page.evaluate("typeof window.__pwn_richtext")
    hv = hidden.input_value()
    add("<script> in paste does NOT execute", pwn == "undefined", f"window.__pwn={pwn}")
    add("<script> tag stripped from emit", "<script" not in hv.lower(), hv[:200])

    # 5. h1/h4 normalised on paste (per IR allowlist).
    page.evaluate(
        """() => {
            const ed = document.querySelector('[data-dz-widget=\\"richtext\\"]')
                .querySelector('[data-dz-editor]');
            ed.focus();
            const r = document.createRange(); r.selectNodeContents(ed);
            const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
            const dt = new DataTransfer();
            dt.setData('text/html', '<h1>top</h1><h4>sub</h4>');
            ed.dispatchEvent(new ClipboardEvent('paste', {
                clipboardData: dt, bubbles: true, cancelable: true
            }));
        }"""
    )
    page.wait_for_timeout(100)
    hv = hidden.input_value()
    add("h1 demoted to h2 on paste", "<h2>" in hv and "<h1>" not in hv, hv[:160])
    add("h4 promoted to h3 on paste", "<h3>" in hv and "<h4>" not in hv, hv[:160])

    # 6. Style/class flood from Word stripped.
    page.evaluate(
        """() => {
            const ed = document.querySelector('[data-dz-widget=\\"richtext\\"]')
                .querySelector('[data-dz-editor]');
            ed.focus();
            const r = document.createRange(); r.selectNodeContents(ed);
            const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
            const html = '<p class=\\"MsoNormal\\" style=\\"color:red\\"><b>Bold</b></p>';
            const dt = new DataTransfer();
            dt.setData('text/html', html);
            ed.dispatchEvent(new ClipboardEvent('paste', {
                clipboardData: dt, bubbles: true, cancelable: true
            }));
        }"""
    )
    page.wait_for_timeout(100)
    hv = hidden.input_value()
    add("style attributes stripped on paste", "style=" not in hv, hv[:160])
    add("class attributes stripped on paste", "class=" not in hv, hv[:160])

    # 7. Lifecycle: htmx-style remount, editor still works.
    page.evaluate(
        """() => {
            const host = document.querySelector('[data-dz-widget=\\"richtext\\"]');
            const clone = host.cloneNode(true);
            host.parentNode.replaceChild(clone, host);
            document.body.dispatchEvent(new CustomEvent('htmx:afterSettle', {
                bubbles: true, detail: { target: clone }
            }));
        }"""
    )
    page.wait_for_timeout(150)
    new_host = page.locator('[data-dz-widget="richtext"]').first
    new_editor = new_host.locator("[data-dz-editor]")
    new_hidden = new_host.locator("input[type=hidden]")
    new_editor.click()
    page.keyboard.type(" remount-ok")
    page.wait_for_timeout(120)
    nv = new_hidden.input_value()
    add("editor functional after htmx-style remount", "remount-ok" in nv, nv[:160])

    return checks


def run_app_fuzz(project_root: Path) -> FuzzReport:
    """Boot `project_root`, fuzz every supported widget, return report.

    Currently exercises: dz-richtext (cycle 1 of this module).
    Future: optimistic-UI forms, combobox, picker, mobile-native swipe.
    """
    project = project_root.name
    report = FuzzReport(project=project)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        report.skipped_reason = f"playwright not installed: {exc}"
        return report

    # Discover the first surface that hosts a rich_text widget by
    # scanning the DSL — keeps the runner generic.
    dsl_text = "\n".join(p.read_text() for p in (project_root / "dsl").glob("*.dsl"))
    if "widget=rich_text" not in dsl_text and "widget: rich_text" not in dsl_text:
        report.skipped_reason = "no rich_text widget declared in this project"
        return report

    # Convention: a `*_create` surface is the easiest to reach. We
    # don't try to be clever — the user can extend this.
    candidate_paths = [
        "/app/showcase/create",
        "/app/contact/create",
        "/app/task/create",
        "/app/ticket/create",
        "/app/comment/create",
        "/app/feedbackreport/create",
    ]

    with _booted_app(project_root) as (base, secret):
        cookies = _authenticate(base, secret, role="admin")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context()
            ctx.add_cookies(
                [
                    {"name": k, "value": v, "url": base, "sameSite": "Lax"}
                    for k, v in cookies.items()
                ]
            )
            page = ctx.new_page()
            page.on(
                "console",
                lambda m: (
                    report.console_errors.append(f"[{m.type}] {m.text}")
                    if m.type == "error" and "fonts.gstatic" not in m.text  # ignore CORS noise
                    else None
                ),
            )
            page.on("pageerror", lambda e: report.page_errors.append(str(e)))

            mounted = False
            for path in candidate_paths:
                page.goto(f"{base}{path}", wait_until="domcontentloaded")
                if page.locator('[data-dz-widget="richtext"]').count() > 0:
                    mounted = True
                    break
            if not mounted:
                report.skipped_reason = "no rich_text mount point reachable on probed surfaces"
                browser.close()
                return report

            report.checks.extend(fuzz_richtext(page, host_index=0))
            browser.close()

    return report
