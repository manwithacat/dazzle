"""
Templates generator for Django Micro backend.

Generates HTML templates for Django views.
Supports UX Semantic Layer for enhanced user experience.
"""

from pathlib import Path

from ....core import ir
from ...base import Generator, GeneratorResult


class TemplatesGenerator(Generator):
    """
    Generate Django HTML templates.

    Creates template files:
    - base.html - Base template with navigation
    - home.html - Home page
    - entity_list.html - List view template
    - entity_detail.html - Detail view template
    - entity_form.html - Create/edit form template
    - entity_confirm_delete.html - Delete confirmation
    """

    def __init__(self, spec: ir.AppSpec, output_dir: Path, app_name: str = "app"):
        """
        Initialize templates generator.

        Args:
            spec: Application specification
            output_dir: Root output directory
            app_name: Name of the Django app
        """
        super().__init__(spec, output_dir)
        self.app_name = app_name

    def generate(self) -> GeneratorResult:
        """Generate template files."""
        result = GeneratorResult()

        # Create templates directory structure
        templates_dir = self.output_dir / self.app_name / "templates"
        app_templates_dir = templates_dir / self.app_name
        self._ensure_dir(app_templates_dir)

        # Generate base template
        base_template = self._generate_base_template()
        base_path = templates_dir / "base.html"
        self._write_file(base_path, base_template)
        result.add_file(base_path)

        # Generate home template
        home_template = self._generate_home_template()
        home_path = app_templates_dir / "home.html"
        self._write_file(home_path, home_template)
        result.add_file(home_path)

        # Generate templates for each entity
        for entity in self.spec.domain.entities:
            entity_templates = self._generate_entity_templates(entity, app_templates_dir)
            result.files_created.extend(entity_templates)

        # Generate workspace templates if any workspaces defined
        for workspace in self.spec.workspaces:
            workspace_templates = self._generate_workspace_templates(workspace, app_templates_dir)
            result.files_created.extend(workspace_templates)

        return result

    def _find_list_surface_for_entity(self, entity_name: str) -> ir.SurfaceSpec | None:
        """Find the list mode surface for an entity."""
        for surface in self.spec.surfaces:
            if surface.entity_ref == entity_name and surface.mode == ir.SurfaceMode.LIST:
                return surface
        return None

    def _generate_base_template(self) -> str:
        """Generate base.html template."""
        # Generate navigation links
        nav_links = self._generate_nav_links()

        return f"""{{% load static %}}
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{% block title %}}{self.spec.name}{{% endblock %}}</title>
    <link rel="stylesheet" href="{{% static 'css/style.css' %}}">
</head>
<body>
    <header>
        <h1><a href="/">{self.spec.name}</a></h1>
        <nav>
            <ul style="list-style: none; padding: 0; display: flex; gap: 20px;">
{nav_links}
            </ul>
        </nav>
    </header>

    <main class="container">
        {{% if messages %}}
        <ul class="messages">
            {{% for message in messages %}}
            <li class="{{{{ message.tags }}}}">{{{{ message }}}}</li>
            {{% endfor %}}
        </ul>
        {{% endif %}}

        {{% block content %}}
        {{% endblock %}}
    </main>

    <footer style="margin-top: 50px; padding: 20px 0; border-top: 1px solid #ddd; text-align: center; color: #666;">
        <p>Generated with DAZZLE</p>
    </footer>
</body>
</html>
"""

    def _generate_nav_links(self) -> str:
        """Generate navigation links for entities and system routes."""
        lines = []

        # Add entity links
        for entity in self.spec.domain.entities:
            entity_lower = entity.name.lower()
            label = entity.title or entity.name
            lines.append(
                f"                <li><a href=\"{{% url '{entity_lower}-list' %}}\">{label}s</a></li>"
            )

        # Add system route: Admin interface
        if lines:  # Only add separator if we have entity links
            lines.append(
                '                <li style="border-left: 1px solid #ddd; margin-left: 10px; padding-left: 20px;"><a href="/admin/">Admin</a></li>'
            )
        else:
            lines.append('                <li><a href="/admin/">Admin</a></li>')

        return "\n".join(lines)

    def _generate_home_template(self) -> str:
        """Generate home.html template."""
        entity_cards = self._generate_entity_cards()

        return f"""{{% extends "base.html" %}}
{{% load static %}}

{{% block title %}}{self.spec.name} - Home{{% endblock %}}

{{% block content %}}
<div>
    <h2>Welcome to {self.spec.name}</h2>


    <div style="margin-top: 30px;">
        <h3>Available Resources</h3>
{entity_cards}
    </div>

    <div style="margin-top: 40px;">
        <h3>System Tools</h3>
        <div class="card" style="border-left: 3px solid #4a90e2;">
            <h2>Admin Dashboard</h2>
            <p>Access the admin interface to manage data, view logs, and configure settings.</p>
            <a href="/admin/" class="btn">Open Admin</a>
        </div>
    </div>
</div>
{{% endblock %}}
"""

    def _generate_entity_cards(self) -> str:
        """Generate entity cards for home page."""
        cards = []
        for entity in self.spec.domain.entities:
            entity_lower = entity.name.lower()
            label = entity.title or entity.name
            cards.append(
                f"""        <div class="card">
            <h2>{label}s</h2>
            <p>Manage {label.lower()}s in the system.</p>
            <a href="{{% url '{entity_lower}-list' %}}" class="btn">View {label}s</a>
            <a href="{{% url '{entity_lower}-create' %}}" class="btn btn-secondary">Create New</a>
        </div>"""
            )
        return "\n".join(cards)

    def _generate_entity_templates(self, entity: ir.EntitySpec, templates_dir: Path) -> list[Path]:
        """Generate all templates for an entity."""
        created_files = []
        entity_lower = entity.name.lower()

        # List template
        list_template = self._generate_list_template(entity)
        list_path = templates_dir / f"{entity_lower}_list.html"
        self._write_file(list_path, list_template)
        created_files.append(list_path)

        # Detail template
        detail_template = self._generate_detail_template(entity)
        detail_path = templates_dir / f"{entity_lower}_detail.html"
        self._write_file(detail_path, detail_template)
        created_files.append(detail_path)

        # Form template (for create and edit)
        form_template = self._generate_form_template(entity)
        form_path = templates_dir / f"{entity_lower}_form.html"
        self._write_file(form_path, form_template)
        created_files.append(form_path)

        # Delete confirmation template
        delete_template = self._generate_delete_template(entity)
        delete_path = templates_dir / f"{entity_lower}_confirm_delete.html"
        self._write_file(delete_path, delete_template)
        created_files.append(delete_path)

        return created_files

    def _generate_list_template(self, entity: ir.EntitySpec) -> str:
        """Generate list view template with UX Semantic Layer support."""
        entity_lower = entity.name.lower()
        label = entity.title or entity.name

        # Find the list surface for this entity to get UX spec
        list_surface = self._find_list_surface_for_entity(entity.name)
        ux_spec = list_surface.ux if list_surface else None

        # Determine display fields
        if ux_spec and ux_spec.show:
            # Use UX spec show list
            display_field_names = ux_spec.show
            display_fields = [f for f in entity.fields if f.name in display_field_names]
            # Maintain order from show list
            field_order = {name: i for i, name in enumerate(display_field_names)}
            display_fields.sort(key=lambda f: field_order.get(f.name, 999))
        else:
            # Default: first 5 fields
            display_fields = list(entity.fields[:5])

        # Generate table headers
        table_headers = "\n".join(
            f"                <th>{f.name.replace('_', ' ').title()}</th>" for f in display_fields
        )

        # Generate table cells with potential attention signal styling
        table_cells = self._generate_table_cells(entity, display_fields, ux_spec)

        # Generate filter/search controls if UX spec defines them
        filter_controls = self._generate_filter_controls(entity, ux_spec)

        # Get purpose and empty message from UX spec
        purpose_html = ""
        if ux_spec and ux_spec.purpose:
            purpose_html = f'\n    <p class="purpose-text">{ux_spec.purpose}</p>'

        empty_message = f"No {label.lower()}s yet."
        if ux_spec and ux_spec.empty_message:
            empty_message = ux_spec.empty_message

        # Generate row class logic for attention signals
        row_class_logic = self._generate_attention_row_class(entity_lower, ux_spec)

        return f"""{{% extends "base.html" %}}

{{% block title %}}{label}s{{% endblock %}}

{{% block content %}}
<div>
    <h2>{label}s</h2>{purpose_html}
    <a href="{{% url '{entity_lower}-create' %}}" class="btn">Create New {label}</a>
{filter_controls}
    <table style="margin-top: 20px; width: 100%; border-collapse: collapse;">
        <thead>
            <tr>
{table_headers}
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {{% for {entity_lower} in {entity_lower}s %}}
            <tr{row_class_logic}>
{table_cells}
                <td>
                    <a href="{{% url '{entity_lower}-detail' {entity_lower}.pk %}}">View</a> |
                    <a href="{{% url '{entity_lower}-update' {entity_lower}.pk %}}">Edit</a> |
                    <a href="{{% url '{entity_lower}-delete' {entity_lower}.pk %}}">Delete</a>
                </td>
            </tr>
            {{% empty %}}
            <tr>
                <td colspan="{len(display_fields) + 1}" class="empty-state">{empty_message} <a href="{{% url '{entity_lower}-create' %}}">Create one</a>.</td>
            </tr>
            {{% endfor %}}
        </tbody>
    </table>

    {{% if is_paginated %}}
    <div class="pagination" style="margin-top: 20px;">
        {{% if page_obj.has_previous %}}
        <a href="?page=1">&laquo; first</a>
        <a href="?page={{{{ page_obj.previous_page_number }}}}">previous</a>
        {{% endif %}}

        <span>Page {{{{ page_obj.number }}}} of {{{{ page_obj.paginator.num_pages }}}}</span>

        {{% if page_obj.has_next %}}
        <a href="?page={{{{ page_obj.next_page_number }}}}">next</a>
        <a href="?page={{{{ page_obj.paginator.num_pages }}}}">last &raquo;</a>
        {{% endif %}}
    </div>
    {{% endif %}}
</div>
{{% endblock %}}
"""

    def _generate_table_cells(
        self,
        entity: ir.EntitySpec,
        display_fields: list[ir.FieldSpec],
        ux_spec: ir.UXSpec | None,
    ) -> str:
        """Generate table cells, potentially with attention signal indicators."""
        entity_lower = entity.name.lower()
        cells = []

        for field in display_fields:
            cell_content = f"{{{{ {entity_lower}.{field.name} }}}}"
            cells.append(f"                <td>{cell_content}</td>")

        return "\n".join(cells)

    def _generate_filter_controls(self, entity: ir.EntitySpec, ux_spec: ir.UXSpec | None) -> str:
        """Generate filter and search controls from UX spec."""
        if not ux_spec:
            return ""

        controls = []

        # Search box if search fields defined
        if ux_spec.search:
            search_placeholder = f"Search {', '.join(ux_spec.search)}..."
            controls.append(
                f"""
    <div class="search-box" style="margin-top: 15px;">
        <form method="get" style="display: inline-flex; gap: 10px;">
            <input type="text" name="q" placeholder="{search_placeholder}"
                   value="{{{{ request.GET.q }}}}" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
            <button type="submit" class="btn btn-secondary">Search</button>
            {{% if request.GET.q %}}<a href="?" class="btn btn-secondary">Clear</a>{{% endif %}}
        </form>
    </div>"""
            )

        # Filter dropdowns if filter fields defined
        if ux_spec.filter:
            filter_fields = []
            for field_name in ux_spec.filter:
                field = next((f for f in entity.fields if f.name == field_name), None)
                if field and field.type.kind == ir.FieldTypeKind.ENUM:
                    # Generate dropdown for enum fields
                    options = "".join(
                        f'<option value="{v}" {{%% if request.GET.{field_name} == "{v}" %%}}selected{{%% endif %%}}>{v.replace("_", " ").title()}</option>'
                        for v in (field.type.enum_values or [])
                    )
                    filter_fields.append(
                        f"""
            <select name="{field_name}" onchange="this.form.submit()" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                <option value="">All {field_name.replace("_", " ").title()}s</option>
                {options}
            </select>"""
                    )

            if filter_fields:
                controls.append(
                    f"""
    <div class="filter-controls" style="margin-top: 10px;">
        <form method="get" style="display: inline-flex; gap: 10px; align-items: center;">
            <span style="color: #666;">Filter:</span>{"".join(filter_fields)}
        </form>
    </div>"""
                )

        return "".join(controls)

    def _generate_attention_row_class(self, entity_lower: str, ux_spec: ir.UXSpec | None) -> str:
        """Generate Django template logic for attention signal row classes."""
        if not ux_spec or not ux_spec.attention_signals:
            return ""

        # Generate conditional class based on attention signals
        # Priority order: critical > warning > notice > info
        conditions = []

        for signal in ux_spec.attention_signals:
            django_condition = self._condition_to_django(signal.condition, entity_lower)
            if django_condition:
                level_class = f"attention-{signal.level.value}"
                conditions.append((django_condition, level_class))

        if not conditions:
            return ""

        # Build nested if/elif chain
        result_parts = []
        for i, (cond, cls) in enumerate(conditions):
            if i == 0:
                result_parts.append(f'{{% if {cond} %}} class="{cls}"')
            else:
                result_parts.append(f'{{% elif {cond} %}} class="{cls}"')

        result_parts.append("{% endif %}")
        return " " + "".join(result_parts)

    def _condition_to_django(self, condition: ir.ConditionExpr, entity_lower: str) -> str | None:
        """Convert a condition expression to Django template syntax."""
        if condition.comparison:
            return self._comparison_to_django(condition.comparison, entity_lower)
        elif condition.is_compound and condition.left and condition.right:
            left = self._condition_to_django(condition.left, entity_lower)
            right = self._condition_to_django(condition.right, entity_lower)
            if left and right:
                op = condition.operator.value if condition.operator else "and"  # "and" or "or"
                return f"({left} {op} {right})"
        return None

    def _comparison_to_django(self, comparison: ir.Comparison, entity_lower: str) -> str | None:
        """Convert a single comparison to Django template syntax."""
        # Handle field references
        if comparison.field:
            left_side = f"{entity_lower}.{comparison.field}"
        elif comparison.function:
            # Handle function calls like days_since(field)
            func_name = comparison.function.name
            func_arg = comparison.function.argument
            if func_name == "days_since":
                # Django doesn't have built-in days_since, use custom filter
                left_side = f"{entity_lower}.{func_arg}|days_since"
            else:
                # Unknown function, skip
                return None
        else:
            return None

        # Handle operator
        op_map = {
            ir.ComparisonOperator.EQUALS: "==",
            ir.ComparisonOperator.NOT_EQUALS: "!=",
            ir.ComparisonOperator.GREATER_THAN: ">",
            ir.ComparisonOperator.LESS_THAN: "<",
            ir.ComparisonOperator.GREATER_EQUAL: ">=",
            ir.ComparisonOperator.LESS_EQUAL: "<=",
        }

        if comparison.operator == ir.ComparisonOperator.IN:
            # Handle "in" operator
            if comparison.value and comparison.value.values:
                values = ", ".join(
                    f'"{v}"' if isinstance(v, str) else str(v) for v in comparison.value.values
                )
                return f"{left_side} in [{values}]"
            return None
        elif comparison.operator == ir.ComparisonOperator.IS:
            # Handle "is null" / "is not null"
            if comparison.value and comparison.value.literal is None:
                return f"{left_side} is None"
            return None

        django_op = op_map.get(comparison.operator)
        if not django_op:
            return None

        # Handle right side value
        if comparison.value:
            if comparison.value.literal is not None:
                val = comparison.value.literal
                if isinstance(val, str):
                    right_side = f'"{val}"'
                elif isinstance(val, bool):
                    right_side = "True" if val else "False"
                else:
                    right_side = str(val)
            else:
                return None
        else:
            return None

        return f"{left_side} {django_op} {right_side}"

    def _generate_workspace_templates(
        self, workspace: ir.WorkspaceSpec, templates_dir: Path
    ) -> list[Path]:
        """Generate templates for a workspace dashboard."""
        created_files = []
        workspace_lower = workspace.name.lower().replace(" ", "_")

        # Generate workspace dashboard template
        dashboard_template = self._generate_workspace_dashboard(workspace)
        dashboard_path = templates_dir / f"{workspace_lower}_dashboard.html"
        self._write_file(dashboard_path, dashboard_template)
        created_files.append(dashboard_path)

        return created_files

    def _generate_workspace_dashboard(self, workspace: ir.WorkspaceSpec) -> str:
        """Generate a workspace dashboard template."""
        title = workspace.title or workspace.name

        # Generate region cards
        region_cards = []
        for region in workspace.regions:
            region_name = region.name or region.source.split(".")[-1]
            region_title = region_name.replace("_", " ").title()

            # Determine display mode class
            display_class = ""
            if region.display == ir.DisplayMode.GRID:
                display_class = " grid-display"
            elif region.display == ir.DisplayMode.TIMELINE:
                display_class = " timeline-display"

            # Generate aggregates if defined
            aggregates_html = ""
            if region.aggregates:
                agg_items = []
                for agg in region.aggregates:
                    agg_items.append(
                        f'<span class="aggregate-item">{{{{ {region_name}_aggregates.{agg} }}}}</span>'
                    )
                aggregates_html = f"""
            <div class="region-aggregates">
                {"".join(agg_items)}
            </div>"""

            # Generate limit info
            limit_info = ""
            if region.limit:
                limit_info = f' <span class="limit-info">(showing up to {region.limit})</span>'

            region_cards.append(
                f"""
        <div class="workspace-region{display_class}">
            <h3>{region_title}{limit_info}</h3>{aggregates_html}
            <div class="region-content">
                {{%% for item in {region_name}_items %%}}
                <div class="region-item">
                    {{{{ item }}}}
                </div>
                {{%% empty %%}}
                <p class="empty-state">No items</p>
                {{%% endfor %%}}
            </div>
        </div>"""
            )

        purpose_html = ""
        if workspace.purpose:
            purpose_html = f'\n    <p class="purpose-text">{workspace.purpose}</p>'

        return f"""{{% extends "base.html" %}}

{{% block title %}}{title}{{% endblock %}}

{{% block content %}}
<div class="workspace-dashboard">
    <h2>{title}</h2>{purpose_html}

    <div class="workspace-regions">
{"".join(region_cards)}
    </div>
</div>
{{% endblock %}}
"""

    def _generate_detail_template(self, entity: ir.EntitySpec) -> str:
        """Generate detail view template."""
        entity_lower = entity.name.lower()
        label = entity.title or entity.name

        # Generate field display
        field_rows = "\n".join(
            f"        <tr>\n            <th>{f.name.replace('_', ' ').title()}</th>\n            <td>{{{{ {entity_lower}.{f.name} }}}}</td>\n        </tr>"
            for f in entity.fields
        )

        return f"""{{% extends "base.html" %}}

{{% block title %}}{label} Details{{% endblock %}}

{{% block content %}}
<div>
    <h2>{label} Details</h2>

    <table style="margin-top: 20px;">
{field_rows}
    </table>

    <div style="margin-top: 20px;">
        <a href="{{% url '{entity_lower}-update' {entity_lower}.pk %}}" class="btn">Edit</a>
        <a href="{{% url '{entity_lower}-delete' {entity_lower}.pk %}}" class="btn btn-danger">Delete</a>
        <a href="{{% url '{entity_lower}-list' %}}" class="btn btn-secondary">Back to List</a>
    </div>
</div>
{{% endblock %}}
"""

    def _generate_form_template(self, entity: ir.EntitySpec) -> str:
        """Generate form template for create and edit."""
        entity_lower = entity.name.lower()
        label = entity.title or entity.name

        return f"""{{% extends "base.html" %}}

{{% block title %}}{label} Form{{% endblock %}}

{{% block content %}}
<div>
    <h2>{{% if form.instance.pk %}}Edit{{% else %}}Create{{% endif %}} {label}</h2>

    <form method="post" style="margin-top: 20px;">
        {{% csrf_token %}}

        {{% if form.non_field_errors %}}
        <div class="errors">
            {{{{ form.non_field_errors }}}}
        </div>
        {{% endif %}}

        {{{{ form.as_p }}}}

        <div style="margin-top: 20px;">
            <button type="submit" class="btn">Save</button>
            <a href="{{% url '{entity_lower}-list' %}}" class="btn btn-secondary">Cancel</a>
        </div>
    </form>
</div>
{{% endblock %}}
"""

    def _generate_delete_template(self, entity: ir.EntitySpec) -> str:
        """Generate delete confirmation template."""
        entity_lower = entity.name.lower()
        label = entity.title or entity.name

        return f"""{{% extends "base.html" %}}

{{% block title %}}Delete {label}{{% endblock %}}

{{% block content %}}
<div>
    <h2>Delete {label}</h2>

    <p>Are you sure you want to delete "{{{{ object }}}}"?</p>

    <form method="post" style="margin-top: 20px;">
        {{% csrf_token %}}
        <button type="submit" class="btn btn-danger">Yes, Delete</button>
        <a href="{{% url '{entity_lower}-detail' object.pk %}}" class="btn btn-secondary">Cancel</a>
    </form>
</div>
{{% endblock %}}
"""
