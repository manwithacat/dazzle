"""Tests for demo data loader."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dazzle.demo_data.loader import (
    DemoDataLoader,
    LoadReport,
    LoadResult,
    find_seed_files,
    read_seed_file,
    topological_sort_entities,
    validate_seed_data,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(name: str, fields: list[tuple[str, str | None]] | None = None):
    """Create a mock EntitySpec with optional FK refs."""
    entity = MagicMock()
    entity.name = name
    entity.fields = []
    for fname, ref in fields or []:
        f = MagicMock()
        f.name = fname
        f.required = fname != "id"
        f.type = MagicMock()
        f.type.ref_entity = ref
        f.type.enum_values = None
        entity.fields.append(f)
    return entity


def _make_entity_with_enum(name: str, field_name: str, enum_values: list[str]):
    """Create a mock entity with an enum field."""
    entity = MagicMock()
    entity.name = name
    f = MagicMock()
    f.name = field_name
    f.required = False
    f.type = MagicMock()
    f.type.ref_entity = None
    f.type.enum_values = enum_values
    entity.fields = [f]
    return entity


# ---------------------------------------------------------------------------
# Topological Sort
# ---------------------------------------------------------------------------


class TestTopologicalSort:
    def test_no_deps(self):
        entities = [_make_entity("A"), _make_entity("B"), _make_entity("C")]
        result = topological_sort_entities(entities)
        assert set(result) == {"A", "B", "C"}

    def test_linear_deps(self):
        entities = [
            _make_entity("Child", [("parent_id", "Parent")]),
            _make_entity("Parent", [("id", None)]),
        ]
        result = topological_sort_entities(entities)
        assert result.index("Parent") < result.index("Child")

    def test_diamond_deps(self):
        entities = [
            _make_entity("Root"),
            _make_entity("Left", [("root_id", "Root")]),
            _make_entity("Right", [("root_id", "Root")]),
            _make_entity("Leaf", [("left_id", "Left"), ("right_id", "Right")]),
        ]
        result = topological_sort_entities(entities)
        assert result.index("Root") < result.index("Left")
        assert result.index("Root") < result.index("Right")
        assert result.index("Left") < result.index("Leaf")
        assert result.index("Right") < result.index("Leaf")

    def test_self_reference_ignored(self):
        entities = [_make_entity("Tree", [("parent_id", "Tree")])]
        result = topological_sort_entities(entities)
        assert result == ["Tree"]

    def test_ref_to_unknown_entity_ignored(self):
        entities = [_make_entity("A", [("ext_id", "External")])]
        result = topological_sort_entities(entities)
        assert result == ["A"]


# ---------------------------------------------------------------------------
# Seed File Reading
# ---------------------------------------------------------------------------


class TestReadSeedFile:
    def test_read_csv(self, tmp_path: Path):
        csv_file = tmp_path / "Task.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "title", "done"])
            writer.writeheader()
            writer.writerow({"id": "1", "title": "Test", "done": "false"})
            writer.writerow({"id": "2", "title": "Other", "done": "true"})
        rows = read_seed_file(csv_file)
        assert len(rows) == 2
        assert rows[0]["title"] == "Test"

    def test_read_jsonl(self, tmp_path: Path):
        jsonl_file = tmp_path / "Task.jsonl"
        jsonl_file.write_text(
            json.dumps({"id": "1", "title": "Test"})
            + "\n"
            + json.dumps({"id": "2", "title": "Other"})
            + "\n"
        )
        rows = read_seed_file(jsonl_file)
        assert len(rows) == 2
        assert rows[1]["title"] == "Other"

    def test_unsupported_format(self, tmp_path: Path):
        txt_file = tmp_path / "data.txt"
        txt_file.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported"):
            read_seed_file(txt_file)


# ---------------------------------------------------------------------------
# Find Seed Files
# ---------------------------------------------------------------------------


class TestFindSeedFiles:
    def test_finds_csv_and_jsonl(self, tmp_path: Path):
        (tmp_path / "Task.csv").write_text("id,title\n1,Test\n")
        (tmp_path / "User.jsonl").write_text('{"id":"1"}\n')
        files = find_seed_files(tmp_path)
        assert "Task" in files
        assert "User" in files
        assert files["Task"].suffix == ".csv"
        assert files["User"].suffix == ".jsonl"

    def test_jsonl_overrides_csv(self, tmp_path: Path):
        (tmp_path / "Task.csv").write_text("id,title\n1,Test\n")
        (tmp_path / "Task.jsonl").write_text('{"id":"1","title":"Test"}\n')
        files = find_seed_files(tmp_path)
        assert files["Task"].suffix == ".jsonl"

    def test_empty_dir(self, tmp_path: Path):
        files = find_seed_files(tmp_path)
        assert files == {}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidateSeedData:
    def test_valid_data(self, tmp_path: Path):
        (tmp_path / "Task.csv").write_text("id,title\n1,Test\n")
        entities = [_make_entity("Task", [("id", None), ("title", None)])]
        errors = validate_seed_data(tmp_path, entities)
        assert errors == []

    def test_unknown_columns(self, tmp_path: Path):
        (tmp_path / "Task.csv").write_text("id,title,bogus\n1,Test,x\n")
        entities = [_make_entity("Task", [("id", None), ("title", None)])]
        errors = validate_seed_data(tmp_path, entities)
        assert any("Unknown columns" in e and "bogus" in e for e in errors)

    def test_no_matching_entity(self, tmp_path: Path):
        (tmp_path / "Ghost.csv").write_text("id\n1\n")
        entities = [_make_entity("Task", [("id", None)])]
        errors = validate_seed_data(tmp_path, entities)
        assert any("No matching entity" in e for e in errors)

    def test_fk_reference_check(self, tmp_path: Path):
        (tmp_path / "Parent.csv").write_text("id\naaa\n")
        (tmp_path / "Child.csv").write_text("id,parent_id\n1,missing-id\n")
        entities = [
            _make_entity("Parent", [("id", None)]),
            _make_entity("Child", [("id", None), ("parent_id", "Parent")]),
        ]
        errors = validate_seed_data(tmp_path, entities)
        assert any("missing Parent ID" in e for e in errors)

    def test_enum_validation(self, tmp_path: Path):
        (tmp_path / "Task.csv").write_text("id,status\n1,invalid_status\n")
        entities = [_make_entity_with_enum("Task", "status", ["open", "closed"])]
        errors = validate_seed_data(tmp_path, entities)
        assert any("not in enum" in e for e in errors)


# ---------------------------------------------------------------------------
# LoadResult / LoadReport
# ---------------------------------------------------------------------------


class TestLoadReport:
    def test_summary(self):
        report = LoadReport()
        report.add(LoadResult(entity="Task", created=5, skipped=1, failed=0))
        report.add(LoadResult(entity="User", created=2, skipped=0, failed=1, errors=["err"]))
        assert report.total_created == 7
        assert report.total_skipped == 1
        assert report.total_failed == 1
        summary = report.summary()
        assert "7 created" in summary
        assert "Task" in summary

    def test_to_dict(self):
        report = LoadReport()
        report.add(LoadResult(entity="Task", created=3))
        d = report.to_dict()
        assert d["total_created"] == 3
        assert len(d["entities"]) == 1


# ---------------------------------------------------------------------------
# DemoDataLoader
# ---------------------------------------------------------------------------


class TestDemoDataLoader:
    def test_load_entity_success(self):
        loader = DemoDataLoader(base_url="http://test:8000")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_client.post.return_value = mock_resp
        loader._client = mock_client

        rows = [{"id": "1", "title": "Test"}, {"id": "2", "title": "Other"}]
        result = loader.load_entity("Task", rows)
        assert result.created == 2
        assert result.failed == 0
        assert mock_client.post.call_count == 2

    def test_load_entity_conflict_skipped(self):
        loader = DemoDataLoader(base_url="http://test:8000")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 409
        mock_client.post.return_value = mock_resp
        loader._client = mock_client

        result = loader.load_entity("Task", [{"id": "1"}])
        assert result.skipped == 1
        assert result.created == 0

    def test_load_entity_validation_error(self):
        loader = DemoDataLoader(base_url="http://test:8000")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.json.return_value = {"detail": "bad field"}
        mock_client.post.return_value = mock_resp
        loader._client = mock_client

        result = loader.load_entity("Task", [{"id": "1"}])
        assert result.failed == 1
        assert "bad field" in result.errors[0]

    def test_authenticate_success(self):
        loader = DemoDataLoader(base_url="http://test:8000", email="a@b.com", password="pass")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "tok123"}
        mock_client.post.return_value = mock_resp
        loader._client = mock_client

        loader.authenticate()
        assert loader._token == "tok123"

    def test_authenticate_failure(self):
        loader = DemoDataLoader(base_url="http://test:8000", email="a@b.com", password="bad")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_client.post.return_value = mock_resp
        loader._client = mock_client

        with pytest.raises(RuntimeError, match="Authentication failed"):
            loader.authenticate()

    def test_authenticate_requires_credentials(self):
        loader = DemoDataLoader(base_url="http://test:8000")
        with pytest.raises(RuntimeError, match="Email and password required"):
            loader.authenticate()

    def test_load_all_respects_order(self, tmp_path: Path):
        # Create seed files
        (tmp_path / "Parent.csv").write_text("id,name\n1,P1\n")
        (tmp_path / "Child.csv").write_text("id,parent_id\n1,1\n")

        loader = DemoDataLoader(base_url="http://test:8000")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_client.post.return_value = mock_resp
        loader._client = mock_client

        report = loader.load_all(tmp_path, ["Parent", "Child"])
        assert len(report.results) == 2
        assert report.results[0].entity == "Parent"
        assert report.results[1].entity == "Child"

    def test_load_all_with_filter(self, tmp_path: Path):
        (tmp_path / "A.csv").write_text("id\n1\n")
        (tmp_path / "B.csv").write_text("id\n1\n")

        loader = DemoDataLoader(base_url="http://test:8000")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_client.post.return_value = mock_resp
        loader._client = mock_client

        report = loader.load_all(tmp_path, ["A", "B"], entities_filter=["B"])
        assert len(report.results) == 1
        assert report.results[0].entity == "B"

    def test_context_manager(self):
        with DemoDataLoader(base_url="http://test:8000") as loader:
            assert loader._client is None
        # After exit, close was called (no error even if no client)

    def test_headers_with_token(self):
        loader = DemoDataLoader(base_url="http://test:8000")
        loader._token = "tok123"
        headers = loader._headers()
        assert headers["Authorization"] == "Bearer tok123"

    def test_headers_without_token(self):
        loader = DemoDataLoader(base_url="http://test:8000")
        headers = loader._headers()
        assert "Authorization" not in headers
