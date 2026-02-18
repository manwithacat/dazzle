"""
Knowledge Graph mixin for test result persistence.

Stores test run history and individual test case results in SQLite,
enabling trend analysis, regression detection, and failure pattern queries.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._protocol import KGStoreProtocol


class KnowledgeGraphTestResults:
    """Mixin providing test result persistence methods."""

    # =========================================================================
    # Write
    # =========================================================================

    def save_test_run(
        self: KGStoreProtocol,
        *,
        run_id: str,
        project_name: str,
        dsl_hash: str,
        started_at: float,
        completed_at: float | None = None,
        total_tests: int = 0,
        passed: int = 0,
        failed: int = 0,
        skipped: int = 0,
        errors: int = 0,
        success_rate: float | None = None,
        tests_generated: int = 0,
        trigger: str = "manual",
        previous_dsl_hash: str | None = None,
    ) -> None:
        """Insert a test_runs row."""
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO test_runs
                    (id, project_name, dsl_hash, previous_dsl_hash,
                     started_at, completed_at,
                     total_tests, passed, failed, skipped, errors,
                     success_rate, tests_generated, trigger)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    project_name,
                    dsl_hash,
                    previous_dsl_hash,
                    started_at,
                    completed_at,
                    total_tests,
                    passed,
                    failed,
                    skipped,
                    errors,
                    success_rate,
                    tests_generated,
                    trigger,
                ),
            )
            conn.commit()
        finally:
            self._close_connection(conn)

    def save_test_case(
        self: KGStoreProtocol,
        *,
        run_id: str,
        test_id: str,
        title: str,
        category: str,
        result: str,
        duration_ms: float = 0.0,
        error_message: str | None = None,
        failure_type: str | None = None,
        entities: list[str] | None = None,
        persona: str | None = None,
        failed_step_json: str | None = None,
    ) -> None:
        """Insert a single test_cases row."""
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO test_cases
                    (run_id, test_id, title, category, result,
                     duration_ms, error_message, failure_type,
                     entities, persona, failed_step_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    test_id,
                    title,
                    category,
                    result,
                    duration_ms,
                    error_message,
                    failure_type,
                    json.dumps(entities) if entities else None,
                    persona,
                    failed_step_json,
                ),
            )
            conn.commit()
        finally:
            self._close_connection(conn)

    def save_test_cases_batch(
        self: KGStoreProtocol,
        run_id: str,
        cases: list[dict[str, Any]],
    ) -> int:
        """Batch-insert test cases via executemany. Returns rows inserted."""
        if not cases:
            return 0
        rows = [
            (
                run_id,
                c["test_id"],
                c["title"],
                c["category"],
                c["result"],
                c.get("duration_ms", 0.0),
                c.get("error_message"),
                c.get("failure_type"),
                json.dumps(c["entities"]) if c.get("entities") else None,
                c.get("persona"),
                c.get("failed_step_json"),
            )
            for c in cases
        ]
        conn = self._get_connection()
        try:
            conn.executemany(
                """
                INSERT INTO test_cases
                    (run_id, test_id, title, category, result,
                     duration_ms, error_message, failure_type,
                     entities, persona, failed_step_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
            return len(rows)
        finally:
            self._close_connection(conn)

    # =========================================================================
    # Read
    # =========================================================================

    def get_test_runs(
        self: KGStoreProtocol,
        project_name: str | None = None,
        limit: int = 20,
        since: float | None = None,
        dsl_hash: str | None = None,
    ) -> list[dict[str, Any]]:
        """List recent test runs, newest first."""
        conditions: list[str] = []
        params: list[Any] = []

        if project_name:
            conditions.append("project_name = ?")
            params.append(project_name)
        if since is not None:
            conditions.append("started_at >= ?")
            params.append(since)
        if dsl_hash:
            conditions.append("dsl_hash = ?")
            params.append(dsl_hash)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        conn = self._get_connection()
        try:
            rows = conn.execute(
                f"SELECT * FROM test_runs {where} ORDER BY started_at DESC LIMIT ?",
                params,
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_connection(conn)

    def get_test_cases(
        self: KGStoreProtocol,
        run_id: str,
        result_filter: str | None = None,
        category_filter: str | None = None,
        failure_type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get test cases for a specific run, with optional filters."""
        conditions = ["run_id = ?"]
        params: list[Any] = [run_id]

        if result_filter:
            conditions.append("result = ?")
            params.append(result_filter)
        if category_filter:
            conditions.append("category = ?")
            params.append(category_filter)
        if failure_type_filter:
            conditions.append("failure_type = ?")
            params.append(failure_type_filter)

        where = " AND ".join(conditions)

        conn = self._get_connection()
        try:
            rows = conn.execute(
                f"SELECT * FROM test_cases WHERE {where} ORDER BY id",
                params,
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_connection(conn)

    # =========================================================================
    # Analytics
    # =========================================================================

    def get_failure_summary(
        self: KGStoreProtocol,
        limit_runs: int = 10,
        project_name: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate failure patterns across recent runs.

        Returns:
            Dict with by_failure_type, by_category, flaky_tests, persistent_failures.
        """
        # Get recent run IDs
        runs = self.get_test_runs(project_name=project_name, limit=limit_runs)  # type: ignore[attr-defined]
        if not runs:
            return {
                "by_failure_type": {},
                "by_category": {},
                "flaky_tests": [],
                "persistent_failures": [],
                "runs_analyzed": 0,
            }

        run_ids = [r["id"] for r in runs]
        placeholders = ",".join("?" for _ in run_ids)

        conn = self._get_connection()
        try:
            # By failure type
            type_rows = conn.execute(
                f"""
                SELECT failure_type, COUNT(*) AS count
                FROM test_cases
                WHERE run_id IN ({placeholders}) AND result IN ('failed', 'error')
                GROUP BY failure_type
                ORDER BY count DESC
                """,
                run_ids,
            ).fetchall()
            by_failure_type = {row["failure_type"] or "unknown": row["count"] for row in type_rows}

            # By category
            cat_rows = conn.execute(
                f"""
                SELECT category, COUNT(*) AS count
                FROM test_cases
                WHERE run_id IN ({placeholders}) AND result IN ('failed', 'error')
                GROUP BY category
                ORDER BY count DESC
                """,
                run_ids,
            ).fetchall()
            by_category = {row["category"]: row["count"] for row in cat_rows}

            # Flaky tests: passed in some runs, failed in others
            flaky_rows = conn.execute(
                f"""
                SELECT test_id,
                       SUM(CASE WHEN result = 'passed' THEN 1 ELSE 0 END) AS pass_count,
                       SUM(CASE WHEN result IN ('failed', 'error') THEN 1 ELSE 0 END) AS fail_count
                FROM test_cases
                WHERE run_id IN ({placeholders})
                GROUP BY test_id
                HAVING pass_count > 0 AND fail_count > 0
                ORDER BY fail_count DESC
                """,
                run_ids,
            ).fetchall()
            flaky_tests = [
                {
                    "test_id": row["test_id"],
                    "pass_count": row["pass_count"],
                    "fail_count": row["fail_count"],
                }
                for row in flaky_rows
            ]

            # Persistent failures: failed in every run they appeared in
            persistent_rows = conn.execute(
                f"""
                SELECT test_id,
                       COUNT(*) AS appearances,
                       SUM(CASE WHEN result IN ('failed', 'error') THEN 1 ELSE 0 END) AS fail_count
                FROM test_cases
                WHERE run_id IN ({placeholders})
                GROUP BY test_id
                HAVING appearances = fail_count AND appearances > 1
                ORDER BY appearances DESC
                """,
                run_ids,
            ).fetchall()
            persistent_failures = [
                {"test_id": row["test_id"], "consecutive_failures": row["appearances"]}
                for row in persistent_rows
            ]

            return {
                "by_failure_type": by_failure_type,
                "by_category": by_category,
                "flaky_tests": flaky_tests,
                "persistent_failures": persistent_failures,
                "runs_analyzed": len(runs),
            }
        finally:
            self._close_connection(conn)

    def detect_regressions(
        self: KGStoreProtocol,
        project_name: str | None = None,
    ) -> dict[str, Any]:
        """Compare two most recent runs. Find tests that went pass→fail.

        Returns:
            Dict with regressions list and run metadata.
        """
        runs = self.get_test_runs(project_name=project_name, limit=2)  # type: ignore[attr-defined]
        if len(runs) < 2:
            return {"regressions": [], "message": "Need at least 2 runs for regression detection"}

        current_run = runs[0]
        previous_run = runs[1]

        conn = self._get_connection()
        try:
            rows = conn.execute(
                """
                SELECT cur.test_id, cur.title, cur.category,
                       cur.error_message, cur.failure_type, cur.failed_step_json
                FROM test_cases cur
                INNER JOIN test_cases prev
                    ON cur.test_id = prev.test_id
                WHERE cur.run_id = ?
                  AND prev.run_id = ?
                  AND cur.result IN ('failed', 'error')
                  AND prev.result = 'passed'
                """,
                (current_run["id"], previous_run["id"]),
            ).fetchall()

            regressions = [
                {
                    "test_id": row["test_id"],
                    "title": row["title"],
                    "category": row["category"],
                    "error_message": row["error_message"],
                    "failure_type": row["failure_type"],
                }
                for row in rows
            ]

            return {
                "regressions": regressions,
                "current_run": current_run["id"],
                "previous_run": previous_run["id"],
                "dsl_changed": current_run["dsl_hash"] != previous_run["dsl_hash"],
            }
        finally:
            self._close_connection(conn)

    def get_test_coverage_trend(
        self: KGStoreProtocol,
        project_name: str | None = None,
        limit_runs: int = 10,
    ) -> list[dict[str, Any]]:
        """Per-run coverage stats for trend analysis."""
        runs = self.get_test_runs(project_name=project_name, limit=limit_runs)  # type: ignore[attr-defined]
        trend = []
        for run in runs:
            total = run["total_tests"]
            trend.append(
                {
                    "run_id": run["id"],
                    "started_at": run["started_at"],
                    "dsl_hash": run["dsl_hash"],
                    "total_tests": total,
                    "passed": run["passed"],
                    "failed": run["failed"],
                    "success_rate": run["success_rate"],
                    "tests_generated": run.get("tests_generated", 0),
                }
            )
        return trend
