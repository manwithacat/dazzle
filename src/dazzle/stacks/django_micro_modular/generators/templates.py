"""
Templates generator for Django Micro backend.

Generates HTML templates for Django views.
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

        return result

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
            cards.append(f"""        <div class="card">
            <h2>{label}s</h2>
            <p>Manage {label.lower()}s in the system.</p>
            <a href="{{% url '{entity_lower}-list' %}}" class="btn">View {label}s</a>
            <a href="{{% url '{entity_lower}-create' %}}" class="btn btn-secondary">Create New</a>
        </div>""")
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
        """Generate list view template."""
        entity_lower = entity.name.lower()
        label = entity.title or entity.name

        # Get display fields (first 5 fields)
        display_fields = list(entity.fields[:5])
        table_headers = "\n".join(
            f"                <th>{f.name.replace('_', ' ').title()}</th>" for f in display_fields
        )
        table_cells = "\n".join(
            f"                <td>{{{{ {entity_lower}.{f.name} }}}}</td>" for f in display_fields
        )

        return f'''{{% extends "base.html" %}}

{{% block title %}}{label}s{{% endblock %}}

{{% block content %}}
<div>
    <h2>{label}s</h2>
    <a href="{{% url '{entity_lower}-create' %}}" class="btn">Create New {label}</a>

    <table style="margin-top: 20px; width: 100%; border-collapse: collapse;">
        <thead>
            <tr>
{table_headers}
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {{% for {entity_lower} in {entity_lower}s %}}
            <tr>
{table_cells}
                <td>
                    <a href="{{% url '{entity_lower}-detail' {entity_lower}.pk %}}">View</a> |
                    <a href="{{% url '{entity_lower}-update' {entity_lower}.pk %}}">Edit</a> |
                    <a href="{{% url '{entity_lower}-delete' {entity_lower}.pk %}}">Delete</a>
                </td>
            </tr>
            {{% empty %}}
            <tr>
                <td colspan="{len(display_fields) + 1}">No {label.lower()}s yet. <a href="{{% url '{entity_lower}-create' %}}">Create one</a>.</td>
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
'''

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
