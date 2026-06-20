from dazzle.http.runtime.access.gated import AccessContext, access_context_from


def test_access_context_bundles_inputs():
    sentinel_auth = object()
    ac = access_context_from(
        auth_context=sentinel_auth,
        entity_name="Project",
        cedar_access_spec="SPEC",
        fk_graph="FK",
        admin_personas=["admin"],
    )
    assert isinstance(ac, AccessContext)
    assert ac.auth_context is sentinel_auth
    assert ac.entity_name == "Project"
    assert ac.cedar_access_spec == "SPEC"
    assert ac.fk_graph == "FK"
    assert ac.admin_personas == ["admin"]
