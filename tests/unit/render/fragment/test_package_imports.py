def test_render_package_importable() -> None:
    import dazzle.render
    import dazzle.render.fragment
    import dazzle.render.fragment.primitives

    assert dazzle.render.__name__ == "dazzle.render"
