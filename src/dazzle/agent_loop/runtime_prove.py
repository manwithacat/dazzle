"""#1605 runtime-layer prove — host readiness beyond static binding.

Does **not** drive a browser or hit a live server. Checks that bound
targets are *implementable* on disk:

- service host module exists, parses, defines the service entrypoint
- entrypoint is not a pure scaffold (``raise NotImplementedError`` only)
- process steps' services are host-ready
- host_route source file exists

Results: ``pass_runtime`` / ``fail_runtime`` / ``skip_runtime``.
A story must ``pass_static`` first or runtime is skipped.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def _read_service_ast(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return None


def _fn_is_scaffold_only(node: ast.AST) -> bool:
    """True if body is only docstring + raise NotImplementedError."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    if len(body) != 1:
        return False
    stmt = body[0]
    return isinstance(stmt, ast.Raise) and (
        stmt.exc is None
        or (
            isinstance(stmt.exc, ast.Call)
            and isinstance(stmt.exc.func, ast.Name)
            and stmt.exc.func.id == "NotImplementedError"
        )
        or (isinstance(stmt.exc, ast.Name) and stmt.exc.id == "NotImplementedError")
    )


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def inspect_host_service(
    project_root: Path,
    service_name: str,
    *,
    expected_inputs: list[str] | None = None,
) -> dict[str, Any]:
    """Host readiness for one domain service name."""
    path = project_root / "services" / f"{service_name}.py"
    out: dict[str, Any] = {
        "service": service_name,
        "path": f"services/{service_name}.py",
        "exists": path.is_file(),
        "ok": False,
        "reasons": [],
    }
    if not path.is_file():
        out["reasons"].append("host_file_missing")
        return out
    tree = _read_service_ast(path)
    if tree is None:
        out["reasons"].append("host_file_unparseable")
        return out
    fn = _find_function(tree, service_name)
    if fn is None:
        out["reasons"].append(f"entrypoint_missing:def {service_name}")
        return out
    out["entrypoint"] = service_name
    if _fn_is_scaffold_only(fn):
        out["reasons"].append("scaffold_not_implemented")
        return out
    if expected_inputs:
        # *args/**kwargs accepted as open contract; else require names present.
        arg_names = {a.arg for a in fn.args.args}
        arg_names |= {a.arg for a in fn.args.kwonlyargs}
        if fn.args.vararg is not None or fn.args.kwarg is not None:
            out["inputs_ok"] = True
        else:
            missing = [n for n in expected_inputs if n not in arg_names and n != "self"]
            out["inputs_ok"] = not missing
            if missing:
                out["reasons"].append(f"inputs_missing:{','.join(missing)}")
                return out
    out["ok"] = True
    out["reasons"].append("host_service_ready")
    return out


def service_contract_diff_deep(project_root: Path, appspec: Any) -> dict[str, Any]:
    """DSL service contracts vs host ``services/*.py`` entrypoints."""
    rows: list[dict[str, Any]] = []
    for svc in getattr(appspec, "domain_services", None) or []:
        name = str(svc.name)
        inputs = [f.name for f in (getattr(svc, "inputs", None) or [])]
        insp = inspect_host_service(project_root, name, expected_inputs=inputs)
        rows.append(
            {
                "service": name,
                "title": getattr(svc, "title", None),
                "inputs": inputs,
                "outputs": [f.name for f in (getattr(svc, "outputs", None) or [])],
                **{k: insp[k] for k in ("exists", "ok", "reasons", "path")},
            }
        )
    host_only: list[str] = []
    services_dir = project_root / "services"
    dsl_names = {str(s.name) for s in (getattr(appspec, "domain_services", None) or [])}
    if services_dir.is_dir():
        for p in services_dir.glob("*.py"):
            if p.name == "__init__.py":
                continue
            if p.stem not in dsl_names:
                host_only.append(p.name)
    ready = sum(1 for r in rows if r.get("ok"))
    missing = sum(1 for r in rows if not r.get("exists"))
    scaffolded = sum(1 for r in rows if "scaffold_not_implemented" in (r.get("reasons") or []))
    return {
        "services": rows,
        "host_only": sorted(host_only),
        "summary": {
            "dsl_count": len(rows),
            "host_ready": ready,
            "host_missing": missing,
            "scaffold_only": scaffolded,
            "orphan_host_py": len(host_only),
        },
        "ok": missing == 0 and scaffolded == 0 and not host_only,
    }


def _process_step_services(proc: Any) -> list[str]:
    names: list[str] = []
    for step in getattr(proc, "steps", None) or []:
        svc = getattr(step, "service", None) or getattr(step, "service_ref", None)
        if svc:
            names.append(str(svc))
    return names


def runtime_prove_one(
    project_root: Path,
    appspec: Any,
    story: Any,
    *,
    static_result: dict[str, Any],
) -> dict[str, Any]:
    """Extend a static prove result with host-readiness checks."""
    base = {
        "story_id": story.story_id,
        "executed_by": static_result.get("executed_by"),
        "static": static_result,
        "evidence_kind": "runtime",
        "evidence": list(static_result.get("evidence") or []),
    }
    static_res = str(static_result.get("result") or "")
    if static_res == "pass_static" and static_result.get("reason") == "narrative_only":
        return {
            **base,
            "result": "skip_runtime",
            "reason": "narrative_only",
            "note": "Honesty mode — no runtime path to prove",
        }
    if not static_res.startswith("pass"):
        return {
            **base,
            "result": "skip_runtime",
            "reason": "static_failed",
            "note": "Fix binding (pass_static) before runtime prove",
        }

    eb_s = str(static_result.get("executed_by") or getattr(story, "executed_by", "") or "").strip()
    evidence = list(base["evidence"])
    ok = True
    reason = "runtime_ready"

    if eb_s.startswith("service."):
        sname = eb_s.split(".", 1)[1]
        inputs: list[str] = []
        for svc in getattr(appspec, "domain_services", None) or []:
            if svc.name == sname:
                inputs = [f.name for f in (svc.inputs or [])]
                break
        insp = inspect_host_service(project_root, sname, expected_inputs=inputs)
        evidence.extend(insp.get("reasons") or [])
        ok = bool(insp.get("ok"))
        reason = "service_host_ready" if ok else f"service_host_not_ready:{sname}"

    elif eb_s.startswith("process."):
        parts = eb_s.split(".")
        pname = parts[1] if len(parts) > 1 else ""
        step_name = parts[3] if len(parts) >= 4 and parts[2] == "step" else None
        proc = next(
            (p for p in (getattr(appspec, "processes", None) or []) if p.name == pname), None
        )
        if proc is None:
            ok = False
            reason = f"process_missing:{pname}"
        else:
            implements = [str(x) for x in (getattr(proc, "implements", None) or [])]
            if story.story_id not in implements and step_name is None:
                # Soft: binding can still be process.X without implements link
                evidence.append("implements_not_listing_story")
            services = _process_step_services(proc)
            if step_name:
                for step in getattr(proc, "steps", None) or []:
                    if getattr(step, "name", None) == step_name:
                        svc = getattr(step, "service", None) or getattr(step, "service_ref", None)
                        services = [str(svc)] if svc else []
                        break
            if not services:
                # Channel-only / human steps — static is enough
                reason = "process_no_service_steps"
                ok = True
                evidence.append("process_steps_without_service")
            else:
                failed_svcs: list[str] = []
                for sn in services:
                    insp = inspect_host_service(project_root, sn)
                    if insp.get("ok"):
                        evidence.append(f"service_ready:{sn}")
                    else:
                        failed_svcs.append(sn)
                        evidence.extend(f"{sn}:{r}" for r in (insp.get("reasons") or []))
                if failed_svcs:
                    ok = False
                    reason = f"process_services_not_ready:{','.join(failed_svcs)}"
                else:
                    reason = "process_services_ready"

    elif eb_s.startswith("surface."):
        # Surface binding is declaration-level; no host file required.
        reason = "surface_declared"
        ok = True
        evidence.append("surface_binding_static_only")

    elif eb_s.lower().startswith("host_route "):
        rest = eb_s.split(None, 1)[1] if " " in eb_s else ""
        bits = rest.split(None, 1)
        method = bits[0].upper() if bits else "GET"
        path = bits[1] if len(bits) > 1 else ""
        try:
            from dazzle.http.runtime.route_overrides import discover_route_overrides

            found = None
            for o in discover_route_overrides(project_root / "routes"):
                if o.method == method and o.path == path:
                    found = o
                    break
            if found is None:
                ok = False
                reason = f"host_route_missing:{method} {path}"
            else:
                src = Path(getattr(found, "source_path", "") or "")
                if src.is_file():
                    tree = _read_service_ast(src)
                    if tree is None:
                        ok = False
                        reason = "host_route_source_unparseable"
                    else:
                        evidence.append(f"host_route_source:{src.name}")
                        reason = "host_route_ready"
                else:
                    ok = False
                    reason = "host_route_source_missing"
        except Exception as exc:
            ok = False
            reason = f"host_route_error:{exc}"
    else:
        ok = False
        reason = f"unsupported_binding:{eb_s}"

    return {
        **base,
        "result": "pass_runtime" if ok else "fail_runtime",
        "reason": reason,
        "evidence": evidence,
        "note": (
            "Host readiness only — not a browser journey. "
            "Scaffolded NotImplementedError services fail_runtime."
        ),
    }


def prove_stories_runtime(
    project_root: Path,
    appspec: Any,
    stories: list[Any],
    *,
    static_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Runtime prove for a list of stories given static results."""
    by_id = {r.get("story_id"): r for r in static_results}
    results = [
        runtime_prove_one(
            project_root,
            appspec,
            s,
            static_result=by_id.get(s.story_id)
            or {
                "story_id": s.story_id,
                "result": "fail_static",
                "reason": "no_static_result",
            },
        )
        for s in stories
    ]
    failed = [r for r in results if str(r.get("result", "")).startswith("fail")]
    skipped = [r for r in results if str(r.get("result", "")).startswith("skip")]
    passed = [r for r in results if str(r.get("result", "")).startswith("pass")]
    return {
        "ok": not failed,
        "operation": "prove",
        "evidence_kind": "runtime",
        "checked": len(results),
        "passed": len(passed),
        "failed": len(failed),
        "skipped": len(skipped),
        "results": results,
        "note": (
            "pass_runtime means host module is ready (not scaffold-only). "
            "Not a browser/e2e journey pass."
        ),
    }
