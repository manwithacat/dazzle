"""_editable_scalar_fields excludes managed + non-string-valued fields (auth Plan 3c.ii)."""

from types import SimpleNamespace

from dazzle.http.runtime.auth.profile_routes import _editable_scalar_fields


def _f(name: str, kind: str):
    return SimpleNamespace(name=name, type=SimpleNamespace(kind=kind))


def test_excludes_managed_and_typed_fields() -> None:
    entity = SimpleNamespace(
        fields=[
            _f("id", "uuid"),  # managed
            _f("tenant_id", "ref"),  # managed (injected)
            _f("identity_id", "uuid"),  # managed (injected)
            _f("created_at", "datetime"),  # managed
            _f("display_name", "str"),  # editable (string-valued)
            _f("bio", "text"),  # editable
            _f("title", "enum"),  # editable
            _f("age", "int"),  # NOT editable yet (typed scalar — would 500 on str write)
            _f("notify", "bool"),  # NOT editable yet
            _f("dob", "date"),  # NOT editable yet
            _f("avatar", "file"),  # NOT editable (non-scalar)
        ]
    )
    editable = {f.name for f in _editable_scalar_fields(entity)}
    assert editable == {"display_name", "bio", "title"}
