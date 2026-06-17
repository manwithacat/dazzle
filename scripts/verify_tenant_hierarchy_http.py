#!/usr/bin/env python3
"""Auth-bootstrap harness + HTTP-level drive for the tenant-hierarchy feature.

Verifies ADR-0036/0037 end-to-end through the **running app's HTTP surface**:
boots `dazzle serve` against a scratch Postgres, bootstraps the auth stack
(users/sessions/memberships) + a non-superuser `staff` user holding ONE membership
at the ROOT tenant (Region), seeds a two-trust tenant tree, then drives the scoped
Report region endpoint with the real session cookie at different host subdomains —
asserting aggregate-at-ancestor / single-at-leaf / no-cross-trust-bleed / deny.

This is the harness that closes the gap the `verify` run hit: `dazzle serve --local`
does not initialise the auth tables, and `/__test__/authenticate` yields a superuser
(which bypasses scope). Here we mint a real non-superuser, membership-scoped session.

Run:  python scripts/verify_tenant_hierarchy_http.py
Needs: a local Postgres reachable as the `james` superuser on localhost:5432.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "fixtures" / "tenant_hierarchy"
ADMIN_URL = "postgresql://james@localhost:5432/postgres"
DB = f"th_http_{uuid.uuid4().hex[:8]}"
DB_URL = f"postgresql://james@localhost:5432/{DB}"
# Full serve binds UI + API + /auth/* on a single port (--port). Hit that.
PORT = 8097
BASE = f"http://127.0.0.1:{PORT}"


def main() -> int:
    import psycopg

    # 1. Fresh scratch DB. DB name is uuid-derived (not user input) — same
    #    nosemgrep posture as the other PG integration tests' scratch-DB DDL.
    with psycopg.connect(ADMIN_URL, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{DB}"')  # nosemgrep
    server: subprocess.Popen | None = None
    failures: list[str] = []
    try:
        # 2. Boot the REAL app (backend-only) against the scratch DB → domain tables.
        env = {
            **os.environ,
            "DATABASE_URL": DB_URL,
            "DAZZLE_SKIP_INFRA_CHECK": "1",
        }
        # 2a. Initialise the auth stack BEFORE boot, so the auth middleware /
        #     RBAC scope enforcement wires up at startup (tables present at boot).
        from dazzle.back.runtime.auth.store import AuthStore

        AuthStore(database_url=DB_URL)._init_db()

        log = open("/tmp/th_http_serve.log", "w")
        # --no-test-mode: test mode sets require_auth=False (workspace_route_builder),
        # which skips scope resolution → all rows. We need real auth + RBAC + scope.
        # Full serve (NOT --backend-only): backend-only does not mount the auth
        # subsystem (router + middleware) — /me 404s there — so scope is never
        # enforced. Full serve mounts auth on the backend; --ui-only off.
        server = subprocess.Popen(
            ["dazzle", "serve", "--local", "--no-test-mode", "--port", str(PORT)],
            cwd=str(FIXTURE),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        for _ in range(60):
            try:
                # Host: localhost is declared canonical in the fixture, so the
                # now-mounted TenantResolutionMiddleware passes it through (the
                # connection target 127.0.0.1 isn't parseable as a canonical host).
                if (
                    httpx.get(
                        f"{BASE}/health", headers={"Host": "localhost"}, timeout=2
                    ).status_code
                    == 200
                ):
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            print("BOOT FAILED — see /tmp/th_http_serve.log")
            return 2
        print(f"[harness] booted {BASE} against {DB}")

        store = AuthStore(database_url=DB_URL)

        # 4. Seed the tenant tree + reports directly (no /__test__ in --no-test-mode).
        ids = {k: str(uuid.uuid4()) for k in ["R", "TA", "TB", "SA1", "SA2", "SB1"]}
        rpt_ids = {t: str(uuid.uuid4()) for t in ("RPTA1a", "RPTA1b", "RPTA2a", "RPTB1a")}
        with psycopg.connect(DB_URL, autocommit=True) as cx:
            cx.execute(
                'INSERT INTO "Region" (id, slug, name, role) VALUES (%s,%s,%s,%s)',
                (ids["R"], "region1", "Region One", "staff"),
            )
            for k, slug, nm in [("TA", "trusta", "Trust A"), ("TB", "trustb", "Trust B")]:
                cx.execute(
                    'INSERT INTO "Trust" (id, slug, name, region) VALUES (%s,%s,%s,%s)',
                    (ids[k], slug, nm, ids["R"]),
                )
            for k, slug, nm, tk in [
                ("SA1", "schoola1", "School A1", "TA"),
                ("SA2", "schoola2", "School A2", "TA"),
                ("SB1", "schoolb1", "School B1", "TB"),
            ]:
                cx.execute(
                    'INSERT INTO "School" (id, slug, name, trust) VALUES (%s,%s,%s,%s)',
                    (ids[k], slug, nm, ids[tk]),
                )
            for title, sch in [
                ("RPTA1a", "SA1"),
                ("RPTA1b", "SA1"),
                ("RPTA2a", "SA2"),
                ("RPTB1a", "SB1"),
            ]:
                cx.execute(
                    'INSERT INTO "Report" (id, title, school) VALUES (%s,%s,%s)',
                    (rpt_ids[title], title, ids[sch]),
                )
        print("[harness] seeded tenant tree (2 trusts, 3 schools, 4 reports)")

        # 5. Mint a NON-superuser `staff` user with ONE membership at the ROOT (Region).
        user = store.create_user(email="staff@hierarchy.test", password="pw-123456")
        assert not getattr(user, "is_superuser", False), "staff user must NOT be superuser"
        m = store.create_membership(tenant_id=ids["R"], identity_id=str(user.id), roles=["staff"])
        session = store.create_session(user, active_membership_id=m.id)
        print(
            f"[harness] minted non-superuser staff session; membership at ROOT Region ({ids['R'][:8]}…)"
        )

        # Drive via http.client: it connects to 127.0.0.1 while sending the EXACT
        # `Host:` header we choose (httpx rewrites Host from the URL authority, so
        # the tenant middleware never saw our subdomain → 0 rows everywhere).
        import http.client

        TITLES = ["RPTA1a", "RPTA1b", "RPTA2a", "RPTB1a"]

        def http_get(path: str, host: str, authed: bool = True) -> tuple[int, str]:
            conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=20)
            headers = {"Host": host}
            if authed:
                headers["Cookie"] = f"dazzle_session={session.id}"
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            body = resp.read().decode("utf-8", "replace")
            conn.close()
            return resp.status, body

        def reports_at(path: str, host: str, authed: bool = True) -> tuple[int, list[str]]:
            sc, body = http_get(path, host, authed)
            return sc, sorted(t for t in TITLES if t in body)

        # 5a0. Does the Host header reach the now-mounted tenant middleware? A bogus
        #      slug under the domain must 404 (resolver miss = the header is seen).
        sc_bogus, _ = http_get("/reports", "nope.hierarchy.example")
        sc_real, _ = http_get("/reports", "schoola1.hierarchy.example")
        print(
            f"\n[diag] Host-header reaches middleware? bogus-slug -> HTTP {sc_bogus} "
            f"(404 = header seen, resolver miss) | real-slug -> HTTP {sc_real}"
        )
        if sc_bogus != 404:
            failures.append(
                f"TenantResolutionMiddleware not engaged: bogus slug -> HTTP {sc_bogus} (want 404)"
            )

        # 5a. Does the bootstrapped session actually AUTHENTICATE?
        sc_a, body_a = http_get("/auth/me", "schoola1.hierarchy.example", authed=True)
        sc_x, _ = http_get("/auth/me", "schoola1.hierarchy.example", authed=False)
        print(f"[diag] /auth/me authed -> HTTP {sc_a} {body_a[:80]!r} | anon -> HTTP {sc_x}")

        # DIAG: what routes exist + what does the leaf host actually render?
        import json as _json

        oc_sc, oc_body = http_get("/openapi.json", "localhost")
        try:
            paths = list(_json.loads(oc_body).get("paths", {}).keys())
            rpaths = [p for p in paths if "report" in p.lower()]
            print(f"[diag] report-ish API paths: {rpaths}")
        except Exception as exc:
            print(f"[diag] openapi parse failed ({oc_sc}): {exc}")
        sc_leaf, leaf_body = http_get("/reports", "schoola1.hierarchy.example", authed=True)
        print(
            f"[diag] schoola1 /reports HTTP {sc_leaf} len={len(leaf_body)} "
            f"hasRPTA1a={'RPTA1a' in leaf_body} snippet={leaf_body[:200]!r}"
        )

        # 6. Auth + fail-closed baseline.
        anon_sc, _ = http_get("/reports", "schoola1.hierarchy.example", authed=False)
        if anon_sc != 401:
            failures.append(f"auth not enforced: anon /reports -> HTTP {anon_sc} (want 401)")
        if sc_a != 200 or "staff@hierarchy.test" not in body_a:
            failures.append("bootstrapped staff session did not authenticate via /auth/me")
        apex_sc, apex_n = reports_at("/reports", "localhost", authed=True)
        if apex_n:  # no tenant bound at the apex → current_tenant unbound → fail-closed
            failures.append(f"scope not fail-closed: apex returned {apex_n} (want [])")

        # 7. THE PROPERTY: per-host current_tenant selects single (leaf) vs aggregate
        #    (ancestor). One root-Region member, driven at different host subdomains.
        #    SA1={RPTA1a,RPTA1b} SA2={RPTA2a} (Trust A); SB1={RPTB1a} (Trust B).
        expected = {
            "schoola1.hierarchy.example": ["RPTA1a", "RPTA1b"],  # single leaf
            "schoola2.hierarchy.example": ["RPTA2a"],  # single leaf
            "trusta.hierarchy.example": ["RPTA1a", "RPTA1b", "RPTA2a"],  # aggregate
            "trustb.hierarchy.example": ["RPTB1a"],  # aggregate (1 school)
            "region1.hierarchy.example": ["RPTA1a", "RPTA1b", "RPTA2a", "RPTB1a"],  # aggregate root
        }
        print("\n[result] per-host current_tenant selection (one root-Region member):")
        for host, want in expected.items():
            sc, found = reports_at("/reports", host, authed=True)
            ok = sc == 200 and found == sorted(want)
            kind = "single " if host.startswith(("schoola", "schoolb")) else "aggreg."
            print(f"  [{'OK ' if ok else 'FAIL'}] {kind} host={host:30} -> HTTP {sc} {found}")
            if not ok:
                failures.append(f"host {host}: HTTP {sc} got {found} want {sorted(want)}")

        # 7a. Cross-trust no-bleed (explicit): Trust A host must NOT surface Trust B's report.
        _, ta_found = reports_at("/reports", "trusta.hierarchy.example", authed=True)
        if "RPTB1a" in ta_found:
            failures.append(f"cross-trust bleed: Trust A host saw Trust B report {ta_found}")
        else:
            print("  [OK ] cross-trust no-bleed: Trust A host excludes Trust B's RPTB1a")

        print("\n[result] HTTP-surface baseline:")
        print(f"  [{'OK ' if anon_sc == 401 else 'FAIL'}] anon /reports denied (HTTP {anon_sc})")
        print(
            f"  [{'OK ' if sc_a == 200 else 'FAIL'}] minted non-superuser staff session authenticates (/auth/me {sc_a})"
        )
        print(
            f"  [{'OK ' if not apex_n else 'FAIL'}] fail-closed at apex (apex -> {len(apex_n)} rows)"
        )
        print(
            f"  [{'OK ' if sc_bogus == 404 else 'FAIL'}] tenant middleware engaged (bogus slug -> {sc_bogus})"
        )

        if failures:
            print("\nRESULT: FAIL\n  - " + "\n  - ".join(failures))
            return 1
        print("\nRESULT: PASS — through real HTTP, a single root-Region member sees")
        print("SINGLE at a School host and AGGREGATE at a Trust/Region host, with no")
        print("cross-trust bleed and fail-closed at the apex. The subdomain→current_tenant")
        print("binding is exercised end-to-end by TenantResolutionMiddleware.")
        return 0
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except Exception:
                server.kill()
        with psycopg.connect(ADMIN_URL, autocommit=True) as a:
            a.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (DB,),
            )
            a.execute(f'DROP DATABASE IF EXISTS "{DB}"')  # nosemgrep


if __name__ == "__main__":
    sys.exit(main())
