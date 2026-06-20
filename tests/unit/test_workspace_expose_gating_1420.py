"""#1420 Slice 2 / S2.3 — workspace-prefixed entity routes respect `expose:`.

Workspaces mount `/{ws}/{plural}` (GET/POST) + `/{ws}/{plural}/{id}`
(GET/PUT/PATCH/DELETE) redirect routes. They must not re-emit a method whose op
is suppressed by the source entity's `expose:` allowlist.
"""

from __future__ import annotations

from dazzle.http.runtime.workspace_route_builder import _workspace_route_methods


class TestWorkspaceRouteMethods:
    def test_none_keeps_all_methods(self) -> None:
        coll, item = _workspace_route_methods(None)
        assert coll == ["GET", "POST"]
        assert item == ["GET", "PUT", "PATCH", "DELETE"]

    def test_list_only_drops_writes_and_read(self) -> None:
        coll, item = _workspace_route_methods(("list",))
        assert coll == ["GET"]  # list survives, create (POST) dropped
        assert item == []  # read/update/delete all dropped

    def test_read_keeps_item_get_only(self) -> None:
        coll, item = _workspace_route_methods(("read",))
        assert coll == []  # no list/create
        assert item == ["GET"]  # read only

    def test_none_expose_empties_both(self) -> None:
        coll, item = _workspace_route_methods(())
        assert coll == []
        assert item == []

    def test_update_maps_put_and_patch(self) -> None:
        _coll, item = _workspace_route_methods(("update",))
        assert item == ["PUT", "PATCH"]
