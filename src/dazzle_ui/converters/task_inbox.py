"""
TaskInbox converter for workspace regions.

Converts task_inbox workspace regions into UI component specifications
for rendering a list of human tasks assigned to the current user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskInboxColumn:
    """Column definition for task inbox."""

    field: str
    label: str
    width: str | None = None
    sortable: bool = True
    format: str | None = None  # "date", "status", "badge"


@dataclass
class TaskInboxConfig:
    """Configuration for task inbox component."""

    # Filtering
    filter_status: list[str] = field(default_factory=lambda: ["pending", "escalated"])
    filter_assignee: str = "current_user"  # "current_user", "all", or specific ID

    # Sorting
    sort_field: str = "due_at"
    sort_direction: str = "asc"

    # Display
    columns: list[TaskInboxColumn] = field(default_factory=list)
    page_size: int = 20
    show_overdue_first: bool = True
    show_process_name: bool = True
    show_urgency_indicator: bool = True

    # Actions
    on_click: str = "navigate_to_task"  # "navigate_to_task", "open_modal"
    show_quick_actions: bool = True

    def __post_init__(self) -> None:
        if not self.columns:
            self.columns = [
                TaskInboxColumn(field="step_name", label="Task", width="25%"),
                TaskInboxColumn(field="process_name", label="Process", width="20%", sortable=True),
                TaskInboxColumn(
                    field="due_at", label="Due", width="15%", format="date", sortable=True
                ),
                TaskInboxColumn(field="status", label="Status", width="10%", format="status"),
                TaskInboxColumn(field="entity_name", label="Entity", width="15%"),
                TaskInboxColumn(field="actions", label="", width="15%", sortable=False),
            ]


class TaskInboxConverter:
    """
    Convert task_inbox workspace region to UI component spec.

    The task_inbox region displays human tasks assigned to the current user
    with filtering, sorting, and quick actions.
    """

    def convert(
        self,
        region_config: dict[str, Any] | None = None,
        persona_filter: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate task inbox component specification.

        Args:
            region_config: Optional configuration from workspace region
            persona_filter: Optional persona-based filter

        Returns:
            Component spec dict for rendering
        """
        config = self._build_config(region_config)

        return {
            "type": "task_inbox",
            "component": "TaskInbox",
            "props": {
                "filter": {
                    "status": config.filter_status,
                    "assignee": config.filter_assignee,
                },
                "sort": {
                    "field": config.sort_field,
                    "direction": config.sort_direction,
                },
                "columns": [
                    {
                        "field": col.field,
                        "label": col.label,
                        "width": col.width,
                        "sortable": col.sortable,
                        "format": col.format,
                    }
                    for col in config.columns
                ],
                "pageSize": config.page_size,
                "showOverdueFirst": config.show_overdue_first,
                "showProcessName": config.show_process_name,
                "showUrgencyIndicator": config.show_urgency_indicator,
                "onClick": config.on_click,
                "showQuickActions": config.show_quick_actions,
            },
            "data_source": {
                "endpoint": "/api/tasks",
                "method": "GET",
                "params": {
                    "status": ",".join(config.filter_status),
                    "assignee_id": (
                        "${current_user.id}"
                        if config.filter_assignee == "current_user"
                        else config.filter_assignee
                    ),
                },
            },
            "actions": [
                {
                    "name": "view_task",
                    "label": "View",
                    "icon": "eye",
                    "handler": "navigateToTask",
                },
                {
                    "name": "complete_task",
                    "label": "Complete",
                    "icon": "check",
                    "handler": "openCompleteModal",
                    "condition": "row.status === 'pending'",
                },
            ],
        }

    def _build_config(self, region_config: dict[str, Any] | None) -> TaskInboxConfig:
        """Build TaskInboxConfig from region configuration."""
        if not region_config:
            return TaskInboxConfig()

        columns = []
        if "columns" in region_config:
            for col_def in region_config["columns"]:
                if isinstance(col_def, dict):
                    columns.append(
                        TaskInboxColumn(
                            field=col_def.get("field", ""),
                            label=col_def.get("label", ""),
                            width=col_def.get("width"),
                            sortable=col_def.get("sortable", True),
                            format=col_def.get("format"),
                        )
                    )
                elif isinstance(col_def, str):
                    # Simple column name
                    columns.append(
                        TaskInboxColumn(
                            field=col_def,
                            label=col_def.replace("_", " ").title(),
                        )
                    )

        return TaskInboxConfig(
            filter_status=region_config.get("filter_status", ["pending", "escalated"]),
            filter_assignee=region_config.get("filter_assignee", "current_user"),
            sort_field=region_config.get("sort_field", "due_at"),
            sort_direction=region_config.get("sort_direction", "asc"),
            columns=columns if columns else None,  # type: ignore
            page_size=region_config.get("page_size", 20),
            show_overdue_first=region_config.get("show_overdue_first", True),
            show_process_name=region_config.get("show_process_name", True),
            show_urgency_indicator=region_config.get("show_urgency_indicator", True),
            on_click=region_config.get("on_click", "navigate_to_task"),
            show_quick_actions=region_config.get("show_quick_actions", True),
        )


def generate_task_inbox_html(config: dict[str, Any]) -> str:
    """
    Generate HTML template for task inbox component.

    Args:
        config: Component spec from TaskInboxConverter.convert()

    Returns:
        HTML string for rendering
    """
    props = config.get("props", {})
    columns = props.get("columns", [])

    column_headers = "\n".join(
        f'<th style="width: {col.get("width", "auto")}">{col.get("label", "")}</th>'
        for col in columns
    )

    return f"""
    <div class="task-inbox" data-component="TaskInbox">
        <div class="task-inbox-header">
            <h3>My Tasks</h3>
            <div class="task-inbox-filters">
                <select id="task-status-filter">
                    <option value="pending,escalated">Active</option>
                    <option value="pending">Pending</option>
                    <option value="escalated">Escalated</option>
                    <option value="completed">Completed</option>
                    <option value="">All</option>
                </select>
            </div>
        </div>
        <table class="task-inbox-table">
            <thead>
                <tr>
                    {column_headers}
                </tr>
            </thead>
            <tbody id="task-inbox-body">
                <!-- Tasks loaded via JavaScript -->
            </tbody>
        </table>
        <div class="task-inbox-pagination" id="task-inbox-pagination">
            <!-- Pagination controls -->
        </div>
    </div>
    """


# Singleton converter instance
task_inbox_converter = TaskInboxConverter()
