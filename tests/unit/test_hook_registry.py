"""Tests for the service hook registry (v0.29.0).

Covers:
- Hook discovery from declaration headers
- Hook registration and filtering
- Pre/post hook integration with CRUDService
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel


class TestHookDiscovery:
    """discover_hooks() parses declaration headers in Python files."""

    def test_discovers_hook_with_declaration(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.hook_registry import discover_hooks

        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "enrich_task.py").write_text(
            "# dazzle:service-hook entity.pre_create\n"
            "# dazzle:entity Task\n\n"
            "def hook(entity_name, data):\n"
            "    data['enriched'] = True\n"
            "    return data\n"
        )
        result = discover_hooks(hooks_dir)
        assert len(result) == 1
        assert result[0].hook_point == "entity.pre_create"
        assert result[0].entity_filter == "Task"
        assert callable(result[0].function)

    def test_ignores_files_without_declaration(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.hook_registry import discover_hooks

        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "helper.py").write_text("def utility(): pass\n")
        result = discover_hooks(hooks_dir)
        assert result == []

    def test_ignores_underscore_files(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.hook_registry import discover_hooks

        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "__init__.py").write_text(
            "# dazzle:service-hook entity.pre_create\ndef hook(entity_name, data): return data\n"
        )
        result = discover_hooks(hooks_dir)
        assert result == []

    def test_warns_on_invalid_hook_point(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.hook_registry import discover_hooks

        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "bad.py").write_text(
            "# dazzle:service-hook entity.invalid_point\ndef hook(): pass\n"
        )
        result = discover_hooks(hooks_dir)
        assert result == []

    def test_warns_on_missing_hook_function(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.hook_registry import discover_hooks

        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "no_func.py").write_text(
            "# dazzle:service-hook entity.pre_create\ndef not_hook(): pass\n"
        )
        result = discover_hooks(hooks_dir)
        assert result == []

    def test_hook_without_entity_filter(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.hook_registry import discover_hooks

        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "global.py").write_text(
            "# dazzle:service-hook entity.post_create\n"
            "def hook(entity_name, entity_id, data, old_data): pass\n"
        )
        result = discover_hooks(hooks_dir)
        assert len(result) == 1
        assert result[0].entity_filter == ""

    def test_nonexistent_dir_returns_empty(self) -> None:
        from dazzle_back.runtime.hook_registry import discover_hooks

        result = discover_hooks(Path("/nonexistent"))
        assert result == []


class TestHookRegistry:
    """HookRegistry registration and filtering."""

    def test_register_and_retrieve(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.hook_registry import HookDescriptor, HookRegistry

        registry = HookRegistry()
        desc = HookDescriptor(
            hook_point="entity.pre_create",
            entity_filter="Task",
            source_path=tmp_path / "hook.py",
            function=lambda *a: None,
        )
        registry.register(desc)
        assert registry.count == 1
        hooks = registry.get_hooks("entity.pre_create", "Task")
        assert len(hooks) == 1

    def test_entity_filter_excludes_non_matching(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.hook_registry import HookDescriptor, HookRegistry

        registry = HookRegistry()
        desc = HookDescriptor(
            hook_point="entity.pre_create",
            entity_filter="Task",
            source_path=tmp_path / "hook.py",
            function=lambda *a: None,
        )
        registry.register(desc)
        # Different entity — should not match
        hooks = registry.get_hooks("entity.pre_create", "Contact")
        assert len(hooks) == 0

    def test_global_hook_matches_all_entities(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.hook_registry import HookDescriptor, HookRegistry

        registry = HookRegistry()
        desc = HookDescriptor(
            hook_point="entity.pre_create",
            entity_filter="",
            source_path=tmp_path / "hook.py",
            function=lambda *a: None,
        )
        registry.register(desc)
        hooks = registry.get_hooks("entity.pre_create", "AnyEntity")
        assert len(hooks) == 1

    def test_summary(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.hook_registry import HookDescriptor, HookRegistry

        registry = HookRegistry()
        for point in ["entity.pre_create", "entity.pre_create", "entity.post_update"]:
            registry.register(
                HookDescriptor(
                    hook_point=point,
                    entity_filter="",
                    source_path=tmp_path / "hook.py",
                    function=lambda *a: None,
                )
            )
        summary = registry.summary()
        assert summary["entity.pre_create"] == 2
        assert summary["entity.post_update"] == 1


class TestBuildRegistry:
    """build_registry() end-to-end."""

    def test_builds_from_hooks_dir(self, tmp_path: Path) -> None:
        from dazzle_back.runtime.hook_registry import build_registry

        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "enrich.py").write_text(
            "# dazzle:service-hook entity.pre_create\n"
            "# dazzle:entity Task\n"
            "def hook(entity_name, data): return data\n"
        )
        (hooks_dir / "log.py").write_text(
            "# dazzle:service-hook entity.post_create\n"
            "def hook(entity_name, entity_id, data, old_data): pass\n"
        )
        registry = build_registry(hooks_dir)
        assert registry.count == 2


class _TaskCreate(BaseModel):
    title: str


class _TaskUpdate(BaseModel):
    title: str | None = None


class _Task(BaseModel):
    id: Any
    title: str


class TestCRUDServicePreHooks:
    """Pre-hooks in CRUDService modify data or cancel operations."""

    def _make_service(self) -> Any:
        from dazzle_back.runtime.service_generator import CRUDService

        return CRUDService(
            entity_name="Task",
            model_class=_Task,
            create_schema=_TaskCreate,
            update_schema=_TaskUpdate,
        )

    async def test_pre_create_hook_modifies_data(self) -> None:
        service = self._make_service()

        def enrich_hook(entity_name: str, data: dict) -> dict:
            data["title"] = data["title"].upper()
            return data

        service.add_pre_create_hook(enrich_hook)
        result = await service.create(data=_TaskCreate(title="hello"))
        assert result.title == "HELLO"

    async def test_pre_create_async_hook(self) -> None:
        service = self._make_service()

        async def async_hook(entity_name: str, data: dict) -> dict:
            data["title"] = "async-" + data["title"]
            return data

        service.add_pre_create_hook(async_hook)
        result = await service.create(data=_TaskCreate(title="test"))
        assert result.title == "async-test"

    async def test_pre_delete_hook_cancels_deletion(self) -> None:
        service = self._make_service()

        # Create an entity first
        entity = await service.create(data=_TaskCreate(title="keep"))

        def prevent_delete(entity_name: str, entity_id: str, data: dict) -> bool:
            return False  # Cancel deletion

        service.add_pre_delete_hook(prevent_delete)
        deleted = await service.delete(entity.id)
        assert deleted is False

        # Entity should still exist
        still_exists = await service.read(entity.id)
        assert still_exists is not None

    async def test_pre_update_hook_modifies_data(self) -> None:
        service = self._make_service()

        entity = await service.create(data=_TaskCreate(title="original"))

        def add_prefix(entity_name: str, entity_id: str, data: dict, old_data: dict) -> dict:
            if "title" in data:
                data["title"] = "[MODIFIED] " + data["title"]
            return data

        service.add_pre_update_hook(add_prefix)
        updated = await service.update(id=entity.id, data=_TaskUpdate(title="new"))
        assert updated is not None
        updated_data = updated.model_dump() if hasattr(updated, "model_dump") else dict(updated)
        assert updated_data["title"] == "[MODIFIED] new"

    async def test_failing_pre_hook_does_not_block(self) -> None:
        service = self._make_service()

        def bad_hook(entity_name: str, data: dict) -> dict:
            raise RuntimeError("Hook error")

        service.add_pre_create_hook(bad_hook)
        # Should still succeed (hook errors are logged, not raised)
        result = await service.create(data=_TaskCreate(title="safe"))
        assert result.title == "safe"
