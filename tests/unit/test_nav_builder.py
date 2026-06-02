from dazzle.ui.converters.nav_builder import NavGroup, NavLink, NavModel


def test_nav_model_is_frozen_and_holds_groups():
    link = NavLink(
        label="Assignments", route="/a/list/Assignment", icon="file", entity="Assignment"
    )
    group = NavGroup(label="Marking", icon=None, collapsed=False, links=(link,))
    model = NavModel(groups=(group,), auto_discovered=False)
    assert model.groups[0].links[0].entity == "Assignment"
    assert model.auto_discovered is False
