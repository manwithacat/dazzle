"""Example index builder for capability discovery.

Scans example apps under ``examples/`` and builds a mapping from capability
key (e.g. ``"widget_rich_text"``) to the places in those apps that demonstrate
the capability.

Each capability is indexed **once per usage** — a distinct ``(app, context)``
pair — because that is the grain at which a reference is worth repeating. The
previous index emitted one ref per *field* and resolved each to the first line
of the app's DSL containing the capability's option value, so ``widget=picker``
in one app produced six refs all pointing at ``app.dsl:1183`` (#1755).

Capabilities indexed:
- Widget annotations on surface fields (``widget=<value>`` options)
- Workspace region display modes: kanban, timeline
- Surface related_groups presence
"""

import logging
from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.ir.workspaces import DisplayMode

from .models import ExampleRef

_log = logging.getLogger(__name__)

# Map widget option values to capability keys
_WIDGET_TO_KEY: dict[str, str] = {
    "rich_text": "widget_rich_text",
    "combobox": "widget_combobox",
    "picker": "widget_picker",
    "slider": "widget_slider",
    "color": "widget_color",
    "tags": "widget_tags",
}

# Map DisplayMode values to capability keys
_LAYOUT_DISPLAY_KEYS: dict[str, str] = {
    "kanban": "layout_kanban",
    "timeline": "layout_timeline",
}


def build_example_index(examples_dir: Path) -> dict[str, list[ExampleRef]]:
    """Scan example apps and return a mapping from capability key to ExampleRefs.

    Args:
        examples_dir: Path to the directory containing example app subdirectories.

    Returns:
        Dict mapping capability key (e.g. ``"widget_rich_text"``) to a list of
        :class:`ExampleRef` objects from apps demonstrating that capability.
        Returns an empty dict if ``examples_dir`` does not exist.
    """
    if not examples_dir.is_dir():
        return {}

    index: dict[str, list[ExampleRef]] = {}

    for app_dir in sorted(examples_dir.iterdir()):
        if not app_dir.is_dir():
            continue
        manifest_path = app_dir / "dazzle.toml"
        if not manifest_path.exists():
            continue

        app_name = app_dir.name
        _log.debug("example_index: scanning %s", app_name)

        try:
            appspec = load_project_appspec(app_dir)
        except Exception as exc:  # noqa: BLE001
            _log.debug("example_index: skipping %s — %s", app_name, exc)
            continue

        # --- Index widget capabilities from surface fields ---
        for surface in appspec.surfaces:
            for section in surface.sections:
                for element in section.elements:
                    widget_val = element.options.get("widget")
                    if widget_val is None:
                        continue
                    cap_key = _WIDGET_TO_KEY.get(str(widget_val))
                    if cap_key is None:
                        continue
                    ref = ExampleRef(
                        app=app_name,
                        context=(
                            f"field {element.field_name!r} widget={widget_val}"
                            f" on surface {surface.name!r}"
                        ),
                    )
                    index.setdefault(cap_key, []).append(ref)

        # --- Index layout capabilities from workspace regions ---
        for workspace in appspec.workspaces:
            for region in workspace.regions:
                display_val = (
                    region.display.value
                    if isinstance(region.display, DisplayMode)
                    else str(region.display)
                )
                cap_key = _LAYOUT_DISPLAY_KEYS.get(display_val)
                if cap_key is None:
                    continue
                ref = ExampleRef(
                    app=app_name,
                    context=(
                        f"workspace {workspace.name!r} region {region.name!r} display={display_val}"
                    ),
                )
                index.setdefault(cap_key, []).append(ref)

        # --- Index related_groups on surfaces ---
        for surface in appspec.surfaces:
            if surface.related_groups:
                ref = ExampleRef(
                    app=app_name,
                    context=f"surface {surface.name!r} has related_groups",
                )
                index.setdefault("layout_related_groups", []).append(ref)

    return index
