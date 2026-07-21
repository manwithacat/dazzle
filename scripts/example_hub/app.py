"""Starlette hub: catalogue + reverse proxy by Host."""

from __future__ import annotations

import html
import logging
from urllib.parse import urljoin

import httpx
from registry import ExampleApp, app_by_name, parse_host
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route
from supervisor import Supervisor

logger = logging.getLogger(__name__)

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
}


def _hub_html(
    apps: list[ExampleApp],
    *,
    hub_port: int,
    hub_domain: str,
    supervisor: Supervisor,
    request_host: str,
) -> str:
    rows = []
    for a in apps:
        st = supervisor.status(a)
        running = st.pid is not None or supervisor.is_port_open(a.port)
        badge = "running" if running else "stopped"
        badge_cls = "ok" if running else "off"
        open_url = f"http://{a.host}:{hub_port}/"
        rows.append(
            f"""
            <tr>
              <td><strong>{html.escape(a.title)}</strong><br>
                <code class="slug">{html.escape(a.name)}</code></td>
              <td><a href="{html.escape(open_url)}">{html.escape(a.host)}</a></td>
              <td><code>{a.port}</code></td>
              <td><span class="badge {badge_cls}">{badge}</span></td>
              <td class="flags">
                {"spec " if a.has_spec else ""}
                {"stories " if a.has_stories else ""}
                {"trial" if a.has_trial else ""}
              </td>
              <td class="actions">
                <a class="btn" href="{html.escape(open_url)}">Open</a>
                <form method="post" action="/_hub/start/{html.escape(a.name)}" style="display:inline">
                  <button type="submit">Start</button>
                </form>
                <form method="post" action="/_hub/stop/{html.escape(a.name)}" style="display:inline">
                  <button type="submit">Stop</button>
                </form>
              </td>
            </tr>
            """
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Dazzle example eval hub</title>
  <style>
    :root {{ font-family: system-ui, sans-serif; color: #0f172a; background: #f8fafc; }}
    body {{ max-width: 960px; margin: 2rem auto; padding: 0 1rem; }}
    h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
    .sub {{ color: #64748b; margin-bottom: 1.5rem; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff;
            border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px #0001; }}
    th, td {{ text-align: left; padding: 0.75rem 1rem; border-bottom: 1px solid #e2e8f0; vertical-align: top; }}
    th {{ background: #f1f5f9; font-size: 0.8rem; text-transform: uppercase; letter-spacing: .04em; color: #475569; }}
    .slug {{ font-size: 0.85rem; color: #64748b; }}
    .badge {{ font-size: 0.75rem; padding: 0.15rem 0.5rem; border-radius: 999px; }}
    .badge.ok {{ background: #dcfce7; color: #166534; }}
    .badge.off {{ background: #fee2e2; color: #991b1b; }}
    .flags {{ font-size: 0.75rem; color: #64748b; }}
    .btn, button {{ font: inherit; font-size: 0.85rem; padding: 0.35rem 0.7rem;
                   border-radius: 6px; border: 1px solid #cbd5e1; background: #fff; cursor: pointer; text-decoration: none; color: inherit; }}
    .btn {{ background: #0f172a; color: #fff; border-color: #0f172a; }}
    .hint {{ margin-top: 1.5rem; padding: 1rem; background: #eff6ff; border-radius: 8px; font-size: 0.9rem; }}
    code {{ background: #f1f5f9; padding: 0.1rem 0.35rem; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>Dazzle example eval hub</h1>
  <p class="sub">Persistent local fleet under <code>{html.escape(hub_domain)}</code>
    · hub host <code>{html.escape(request_host)}</code>
    · port <code>{hub_port}</code></p>
  <table>
    <thead>
      <tr>
        <th>App</th><th>Host</th><th>Backend</th><th>Status</th><th>Artifacts</th><th></th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows) if rows else "<tr><td colspan='6'>No examples found</td></tr>"}
    </tbody>
  </table>
  <div class="hint">
    <strong>DNS:</strong> point <code>*.dazzle.local</code> at <code>127.0.0.1</code>
    (see <code>scripts/example_hub/README.md</code>).
    Without DNS, open the hub at <code>http://127.0.0.1:{hub_port}/</code>
    and use curl <code>-H "Host: simple_task.dazzle.local"</code>.
    First open of an app starts <code>dazzle serve</code> on demand.
  </div>
</body>
</html>
"""


def create_app(
    *,
    apps: list[ExampleApp],
    supervisor: Supervisor,
    hub_port: int = 9080,
    hub_domain: str = "dazzle.local",
    auto_start: bool = True,
) -> Starlette:
    by_name = {a.name: a for a in apps}

    async def hub_index(request: Request) -> Response:
        host = request.headers.get("host", "")
        return HTMLResponse(
            _hub_html(
                apps,
                hub_port=hub_port,
                hub_domain=hub_domain,
                supervisor=supervisor,
                request_host=host,
            )
        )

    async def hub_api(request: Request) -> Response:
        payload = [
            {
                "name": a.name,
                "title": a.title,
                "host": a.host,
                "url": f"http://{a.host}:{hub_port}/",
                "port": a.port,
                "running": supervisor.is_running(a),
                "has_spec": a.has_spec,
                "has_trial": a.has_trial,
                "has_stories": a.has_stories,
                "path": str(a.path),
            }
            for a in apps
        ]
        return JSONResponse({"hub_domain": hub_domain, "hub_port": hub_port, "apps": payload})

    async def hub_start(request: Request) -> Response:
        name = request.path_params["name"]
        app = by_name.get(name)
        if not app:
            return JSONResponse({"error": "unknown app"}, status_code=404)
        st = supervisor.start(app, wait=True)
        if request.headers.get("accept", "").find("json") >= 0:
            return JSONResponse({"app": name, "running": True, "port": st.port, "pid": st.pid})
        return Response(status_code=303, headers={"Location": "/"})

    async def hub_stop(request: Request) -> Response:
        name = request.path_params["name"]
        app = by_name.get(name)
        if not app:
            return JSONResponse({"error": "unknown app"}, status_code=404)
        supervisor.stop(app)
        if request.headers.get("accept", "").find("json") >= 0:
            return JSONResponse({"app": name, "running": False})
        return Response(status_code=303, headers={"Location": "/"})

    async def proxy_or_hub(request: Request) -> Response:
        host = request.headers.get("host")
        slug = parse_host(host, hub_domain=hub_domain)

        # Hub control routes always on any host under /_hub/
        if request.url.path.startswith("/_hub/"):
            # fall through to mounted routes — handled by specific routes
            pass

        if slug is None:
            return await hub_index(request)

        if slug.startswith("?unknown:"):
            unknown = slug.split(":", 1)[1]
            known = ", ".join(a.name for a in apps)
            return HTMLResponse(
                f"<h1>Unknown app host</h1>"
                f"<p><code>{html.escape(unknown)}</code> is not a registered example.</p>"
                f"<p>Known: {html.escape(known)}</p>"
                f"<p><a href='http://{hub_domain}:{hub_port}/'>Back to hub</a></p>",
                status_code=404,
            )

        app = app_by_name(slug, apps)
        if app is None:
            return HTMLResponse(
                f"<h1>Unknown example</h1><p><code>{html.escape(slug)}</code></p>",
                status_code=404,
            )

        if auto_start and not supervisor.is_running(app):
            st = supervisor.start(app, wait=True)
            if not supervisor.is_port_open(app.port):
                return HTMLResponse(
                    f"<h1>Failed to start {html.escape(app.name)}</h1>"
                    f"<p>See log: <code>{html.escape(str(supervisor.log_path(app.name)))}</code></p>"
                    f"<p>pid={st.pid}</p>",
                    status_code=502,
                )

        return await _proxy(request, app)

    async def _proxy(request: Request, app: ExampleApp) -> Response:
        url = urljoin(f"http://127.0.0.1:{app.port}", request.url.path)
        if request.url.query:
            url = f"{url}?{request.url.query}"

        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in HOP_BY_HOP and k.lower() != "host"
        }
        # Preserve public Host for future tenant_host demos; also send backend target.
        headers["host"] = request.headers.get("host", f"{app.host}")
        headers["x-forwarded-host"] = request.headers.get("host", "")
        headers["x-forwarded-proto"] = request.url.scheme
        headers["x-dazzle-eval-hub"] = "1"

        body = await request.body()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                upstream = await client.request(
                    request.method,
                    url,
                    headers=headers,
                    content=body,
                )
        except httpx.RequestError as exc:
            logger.warning("proxy error %s: %s", app.name, exc)
            return HTMLResponse(
                f"<h1>Upstream error</h1><p>{html.escape(app.name)}:{app.port}</p>"
                f"<pre>{html.escape(str(exc))}</pre>",
                status_code=502,
            )

        resp_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in HOP_BY_HOP}
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=resp_headers,
            media_type=upstream.headers.get("content-type"),
        )

    routes = [
        Route("/_hub/api/apps", hub_api, methods=["GET"]),
        Route("/_hub/start/{name}", hub_start, methods=["POST"]),
        Route("/_hub/stop/{name}", hub_stop, methods=["POST"]),
        Route(
            "/{path:path}",
            proxy_or_hub,
            methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        ),
        Route(
            "/", proxy_or_hub, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
        ),
    ]
    return Starlette(routes=routes)


def build_default(
    *,
    showcase_only: bool = False,
    hub_port: int = 9080,
    backend_base: int = 9100,
    auto_start: bool = True,
    test_mode: bool = True,
) -> tuple[Starlette, list[ExampleApp], Supervisor]:
    from registry import discover_apps

    apps = discover_apps(showcase_only=showcase_only, backend_base=backend_base)
    sup = Supervisor(test_mode=test_mode)
    app = create_app(
        apps=apps,
        supervisor=sup,
        hub_port=hub_port,
        auto_start=auto_start,
    )
    return app, apps, sup
