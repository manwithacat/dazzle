"""
Express.js Micro Backend - Single Express app with SQLite.

Generates a complete Express.js application with:
- Express.js web framework
- Sequelize ORM with SQLite
- AdminJS for admin interface
- EJS templates for server-side rendering
- Express Validator for form validation

Perfect for Node.js developers and easy deployment on Vercel, Heroku, Railway.

Output Structure:
    project_name/
        package.json
        server.js
        config/
            database.js
        models/
            index.js
            Task.js
        routes/
            index.js
            tasks.js
        views/
            layout.ejs
            home.ejs
            tasks/
                list.ejs
                detail.ejs
                form.ejs
                delete.ejs
        public/
            css/
                style.css
        admin.js
        .gitignore
        Procfile
        vercel.json
        README.md
"""

from pathlib import Path
from typing import Dict, Any

from . import Backend, BackendCapabilities
from ..core import ir


class ExpressMicroBackend(Backend):
    """
    Express.js Micro backend - single app with SQLite.

    Perfect for:
    - Node.js developers
    - JavaScript-first teams
    - Quick prototyping
    - Easy deployment on Vercel/Heroku
    """

    def get_capabilities(self) -> BackendCapabilities:
        """Return backend capabilities."""
        return BackendCapabilities(
            name="express_micro",
            description="Single Express.js app with SQLite (Node.js alternative to django_micro)",
            output_formats=["javascript", "html", "json"],
        )

    def generate(self, spec: "ir.AppSpec", output_dir: Path, **options) -> None:
        """
        Generate Express.js micro application.

        Args:
            spec: Application specification
            output_dir: Output directory
            **options: Backend options
        """
        self.spec = spec
        self.output_dir = output_dir
        self.options = options

        # Determine project name from spec
        self.project_name = self._get_project_name(spec)
        self.app_name = self.project_name.replace("_", "-")  # npm package name format

        # Create project structure
        self._generate_project_structure()

        # Generate Sequelize models
        self._generate_models()

        # Generate Express routes
        self._generate_routes()

        # Generate EJS templates
        self._generate_templates()

        # Generate main application files
        self._generate_server()
        self._generate_admin()
        self._generate_database_config()

        # Generate deployment configs
        self._generate_package_json()
        self._generate_gitignore()
        self._generate_procfile()
        self._generate_vercel_config()

        # Generate documentation
        self._generate_readme()

    def _get_project_name(self, spec: "ir.AppSpec") -> str:
        """Get project name from spec."""
        if spec.name:
            # Convert to valid identifier
            name = spec.name.lower().replace(" ", "_").replace("-", "_")
            name = "".join(c for c in name if c.isalnum() or c == "_")
            return name or "myapp"
        return "myapp"

    def _generate_project_structure(self) -> None:
        """Create Express.js project directory structure."""
        # Root project directory
        project_root = self.output_dir / self.app_name
        project_root.mkdir(parents=True, exist_ok=True)

        # Config directory
        (project_root / "config").mkdir(exist_ok=True)

        # Models directory
        (project_root / "models").mkdir(exist_ok=True)

        # Routes directory
        (project_root / "routes").mkdir(exist_ok=True)

        # Views directory
        views_dir = project_root / "views"
        views_dir.mkdir(exist_ok=True)

        # Create subdirectories for each entity
        for entity in self.spec.domain.entities:
            entity_lower = entity.name.lower()
            (views_dir / entity_lower).mkdir(exist_ok=True)

        # Public directory
        public_dir = project_root / "public"
        public_dir.mkdir(exist_ok=True)
        css_dir = public_dir / "css"
        css_dir.mkdir(exist_ok=True)

        # Create base CSS
        (css_dir / "style.css").write_text(self._get_base_css())

    def _get_base_css(self) -> str:
        """Generate base CSS (same as django_micro for consistency)."""
        return """/* DAZZLE Express Micro - Base Styles */

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

header {
    border-bottom: 2px solid #007bff;
    margin-bottom: 30px;
    padding-bottom: 10px;
}

header h1 {
    color: #007bff;
    margin: 0;
}

header h1 a {
    color: #007bff;
    text-decoration: none;
}

nav ul {
    list-style: none;
    padding: 0;
    display: flex;
    gap: 20px;
    margin-top: 10px;
}

nav a {
    color: #007bff;
    text-decoration: none;
}

nav a:hover {
    text-decoration: underline;
}

.container {
    padding: 20px 0;
}

.card {
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 20px;
    background: #fff;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.btn {
    display: inline-block;
    padding: 10px 20px;
    background: #007bff;
    color: white;
    text-decoration: none;
    border-radius: 4px;
    border: none;
    cursor: pointer;
}

.btn:hover {
    background: #0056b3;
}

.btn-secondary {
    background: #6c757d;
}

.btn-secondary:hover {
    background: #545b62;
}

.btn-danger {
    background: #dc3545;
}

.btn-danger:hover {
    background: #c82333;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
}

table th,
table td {
    padding: 12px;
    text-align: left;
    border-bottom: 1px solid #ddd;
}

table th {
    background: #f8f9fa;
    font-weight: 600;
}

table tr:hover {
    background: #f8f9fa;
}

form {
    max-width: 600px;
}

.form-group {
    margin-bottom: 20px;
}

.form-group label {
    display: block;
    margin-bottom: 5px;
    font-weight: 600;
}

.form-group input,
.form-group textarea,
.form-group select {
    width: 100%;
    padding: 8px 12px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 14px;
}

.form-group input:focus,
.form-group textarea:focus,
.form-group select:focus {
    outline: none;
    border-color: #007bff;
}

.error {
    color: #dc3545;
    font-size: 0.875em;
    margin-top: 5px;
}

.alert {
    padding: 12px;
    margin-bottom: 20px;
    border-radius: 4px;
}

.alert-success {
    background: #d4edda;
    color: #155724;
    border: 1px solid #c3e6cb;
}

.alert-error {
    background: #f8d7da;
    color: #721c24;
    border: 1px solid #f5c6cb;
}
"""

    def _generate_models(self) -> None:
        """Generate Sequelize models."""
        if not self.spec.domain.entities:
            # Create empty models/index.js
            models_index = self.output_dir / self.app_name / "models" / "index.js"
            models_index.write_text(self._get_empty_models_index())
            return

        # Generate models/index.js
        models_index = self._build_models_index()
        (self.output_dir / self.app_name / "models" / "index.js").write_text(models_index)

        # Generate individual model files
        for entity in self.spec.domain.entities:
            model_code = self._build_model_file(entity)
            model_path = self.output_dir / self.app_name / "models" / f"{entity.name}.js"
            model_path.write_text(model_code)

    def _get_empty_models_index(self) -> str:
        """Generate empty models index."""
        return """const { Sequelize } = require('sequelize');
const path = require('path');

const sequelize = new Sequelize({
  dialect: 'sqlite',
  storage: path.join(__dirname, '..', 'database.sqlite'),
  logging: false
});

const db = {
  sequelize,
  Sequelize
};

module.exports = db;
"""

    def _build_models_index(self) -> str:
        """Build models/index.js with all models."""
        lines = [
            "const { Sequelize } = require('sequelize');",
            "const path = require('path');",
            "",
            "const sequelize = new Sequelize({",
            "  dialect: 'sqlite',",
            "  storage: path.join(__dirname, '..', 'database.sqlite'),",
            "  logging: false",
            "});",
            "",
            "const db = {",
            "  sequelize,",
            "  Sequelize",
            "};",
            ""
        ]

        # Import and initialize models
        for entity in self.spec.domain.entities:
            lines.append(f"db.{entity.name} = require('./{entity.name}')(sequelize, Sequelize.DataTypes);")

        lines.extend([
            "",
            "// Define associations here if needed",
            "",
            "module.exports = db;",
            ""
        ])

        return '\n'.join(lines)

    def _build_model_file(self, entity: "ir.EntitySpec") -> str:
        """Build individual Sequelize model file."""
        lines = [
            "module.exports = (sequelize, DataTypes) => {",
            f"  const {entity.name} = sequelize.define('{entity.name}', {{",
        ]

        # Generate fields
        for field in entity.fields:
            # Skip auto-generated integer IDs (Sequelize creates them)
            if field.is_primary_key and field.type.kind == ir.FieldTypeKind.INT:
                continue

            field_def = self._generate_sequelize_field(field)
            if field_def:
                lines.append(f"    {field_def},")

        lines.append("  }, {")
        lines.append("    tableName: '" + entity.name.lower() + "s',")
        lines.append("    timestamps: true, // createdAt, updatedAt")
        lines.append("  });")
        lines.append("")
        lines.append(f"  return {entity.name};")
        lines.append("};")
        lines.append("")

        return '\n'.join(lines)

    def _generate_sequelize_field(self, field: "ir.FieldSpec") -> str:
        """Generate Sequelize field definition."""
        field_type = field.type
        field_name = field.name

        # Handle UUID primary key
        if field.is_primary_key and field_type.kind == ir.FieldTypeKind.UUID:
            return f"""{field_name}: {{
      type: DataTypes.UUID,
      defaultValue: DataTypes.UUIDV4,
      primaryKey: true
    }}"""

        # Map field type
        sequelize_type = self._map_sequelize_type(field_type)

        parts = [f"{field_name}: {{"]
        parts.append(f"      type: {sequelize_type},")

        # Add constraints
        if not field.is_required:
            parts.append("      allowNull: true,")
        else:
            parts.append("      allowNull: false,")

        if field.is_unique:
            parts.append("      unique: true,")

        if field.default is not None:
            default_val = self._format_js_default(field.default, field_type.kind)
            parts.append(f"      defaultValue: {default_val},")

        # Validation for required string fields
        if field.is_required and field_type.kind == ir.FieldTypeKind.STR:
            parts.append("      validate: { notEmpty: true },")

        # Remove trailing comma from last line
        parts[-1] = parts[-1].rstrip(',')
        parts.append("    }")

        return '\n'.join(parts)

    def _map_sequelize_type(self, field_type: "ir.FieldType") -> str:
        """Map DAZZLE field type to Sequelize type."""
        type_map = {
            ir.FieldTypeKind.STR: f"DataTypes.STRING({field_type.max_length or 255})",
            ir.FieldTypeKind.TEXT: "DataTypes.TEXT",
            ir.FieldTypeKind.INT: "DataTypes.INTEGER",
            ir.FieldTypeKind.DECIMAL: "DataTypes.DECIMAL",
            ir.FieldTypeKind.BOOL: "DataTypes.BOOLEAN",
            ir.FieldTypeKind.DATE: "DataTypes.DATEONLY",
            ir.FieldTypeKind.DATETIME: "DataTypes.DATE",
            ir.FieldTypeKind.UUID: "DataTypes.UUID",
            ir.FieldTypeKind.EMAIL: "DataTypes.STRING",
        }

        return type_map.get(field_type.kind, "DataTypes.STRING")

    def _format_js_default(self, value: Any, field_type_kind: "ir.FieldTypeKind") -> str:
        """Format default value for JavaScript."""
        if isinstance(value, str):
            return f"'{value}'"
        elif isinstance(value, bool):
            return str(value).lower()
        elif value is None:
            return 'null'
        else:
            return str(value)

    def _generate_routes(self) -> None:
        """Generate Express routes."""
        # Generate main routes index
        routes_index = self._build_routes_index()
        (self.output_dir / self.app_name / "routes" / "index.js").write_text(routes_index)

        # Generate routes for each entity
        for entity in self.spec.domain.entities:
            routes_code = self._build_entity_routes(entity)
            entity_lower = entity.name.lower()
            (self.output_dir / self.app_name / "routes" / f"{entity_lower}.js").write_text(routes_code)

    def _build_routes_index(self) -> str:
        """Build routes/index.js."""
        lines = [
            "const express = require('express');",
            "const router = express.Router();",
            "",
            "// Home page",
            "router.get('/', (req, res) => {",
            "  res.render('home', { title: '" + (self.spec.title or self.spec.name or "App") + "' });",
            "});",
            "",
            "module.exports = router;",
            ""
        ]
        return '\n'.join(lines)

    def _build_entity_routes(self, entity: "ir.EntitySpec") -> str:
        """Build routes for an entity."""
        entity_lower = entity.name.lower()
        entity_name = entity.name

        lines = [
            "const express = require('express');",
            "const router = express.Router();",
            "const { body, validationResult } = require('express-validator');",
            f"const {{ {entity_name} }} = require('../models');",
            "",
            "// List all",
            "router.get('/', async (req, res) => {",
            "  try {",
            f"    const {entity_lower}s = await {entity_name}.findAll({{",
            "      order: [['createdAt', 'DESC']]",
            "    });",
            f"    res.render('{entity_lower}/list', {{ {entity_lower}s }});",
            "  } catch (error) {",
            "    res.status(500).send('Error loading data');",
            "  }",
            "});",
            "",
            "// View detail",
            "router.get('/:id', async (req, res) => {",
            "  try {",
            f"    const {entity_lower} = await {entity_name}.findByPk(req.params.id);",
            f"    if (!{entity_lower}) {{",
            "      return res.status(404).send('Not found');",
            "    }",
            f"    res.render('{entity_lower}/detail', {{ {entity_lower} }});",
            "  } catch (error) {",
            "    res.status(500).send('Error loading data');",
            "  }",
            "});",
            "",
            "// Create form",
            "router.get('/new/form', (req, res) => {",
            f"  res.render('{entity_lower}/form', {{ {entity_lower}: {{}}, errors: {{}} }});",
            "});",
            "",
            "// Create (POST)",
            f"router.post('/', {self._get_validation_middleware(entity)}, async (req, res) => {{",
            "  const errors = validationResult(req);",
            "  if (!errors.isEmpty()) {",
            f"    return res.render('{entity_lower}/form', {{",
            f"      {entity_lower}: req.body,",
            "      errors: errors.mapped()",
            "    });",
            "  }",
            "",
            "  try {",
            f"    await {entity_name}.create(req.body);",
            f"    res.redirect('/{entity_lower}');",
            "  } catch (error) {",
            f"    res.render('{entity_lower}/form', {{",
            f"      {entity_lower}: req.body,",
            "      errors: { _error: 'Failed to create' }",
            "    });",
            "  }",
            "});",
            "",
            "// Edit form",
            "router.get('/:id/edit', async (req, res) => {",
            "  try {",
            f"    const {entity_lower} = await {entity_name}.findByPk(req.params.id);",
            f"    if (!{entity_lower}) {{",
            "      return res.status(404).send('Not found');",
            "    }",
            f"    res.render('{entity_lower}/form', {{ {entity_lower}, errors: {{}} }});",
            "  } catch (error) {",
            "    res.status(500).send('Error loading data');",
            "  }",
            "});",
            "",
            "// Update (POST)",
            f"router.post('/:id', {self._get_validation_middleware(entity)}, async (req, res) => {{",
            "  const errors = validationResult(req);",
            "  if (!errors.isEmpty()) {",
            f"    return res.render('{entity_lower}/form', {{",
            f"      {entity_lower}: {{ ...req.body, id: req.params.id }},",
            "      errors: errors.mapped()",
            "    });",
            "  }",
            "",
            "  try {",
            f"    const {entity_lower} = await {entity_name}.findByPk(req.params.id);",
            f"    if (!{entity_lower}) {{",
            "      return res.status(404).send('Not found');",
            "    }",
            f"    await {entity_lower}.update(req.body);",
            f"    res.redirect('/{entity_lower}/' + req.params.id);",
            "  } catch (error) {",
            f"    res.render('{entity_lower}/form', {{",
            f"      {entity_lower}: {{ ...req.body, id: req.params.id }},",
            "      errors: { _error: 'Failed to update' }",
            "    });",
            "  }",
            "});",
            "",
            "// Delete confirmation",
            "router.get('/:id/delete', async (req, res) => {",
            "  try {",
            f"    const {entity_lower} = await {entity_name}.findByPk(req.params.id);",
            f"    if (!{entity_lower}) {{",
            "      return res.status(404).send('Not found');",
            "    }",
            f"    res.render('{entity_lower}/delete', {{ {entity_lower} }});",
            "  } catch (error) {",
            "    res.status(500).send('Error loading data');",
            "  }",
            "});",
            "",
            "// Delete (POST)",
            "router.post('/:id/delete', async (req, res) => {",
            "  try {",
            f"    const {entity_lower} = await {entity_name}.findByPk(req.params.id);",
            f"    if (!{entity_lower}) {{",
            "      return res.status(404).send('Not found');",
            "    }",
            f"    await {entity_lower}.destroy();",
            f"    res.redirect('/{entity_lower}');",
            "  } catch (error) {",
            "    res.status(500).send('Error deleting');",
            "  }",
            "});",
            "",
            "module.exports = router;",
            ""
        ]

        return '\n'.join(lines)

    def _get_validation_middleware(self, entity: "ir.EntitySpec") -> str:
        """Generate express-validator middleware."""
        validators = []

        for field in entity.fields:
            if field.is_primary_key or ir.FieldModifier.AUTO_ADD in field.modifiers:
                continue

            if field.is_required and field.type.kind == ir.FieldTypeKind.STR:
                validators.append(f"body('{field.name}').trim().notEmpty()")
            elif field.type.kind == ir.FieldTypeKind.EMAIL:
                validators.append(f"body('{field.name}').isEmail()")

        if validators:
            return "[\n    " + ",\n    ".join(validators) + "\n  ]"
        return "[]"

    def _generate_templates(self) -> None:
        """Generate EJS templates."""
        views_dir = self.output_dir / self.app_name / "views"

        # Generate layout
        (views_dir / "layout.ejs").write_text(self._get_layout_template())

        # Generate home page
        (views_dir / "home.ejs").write_text(self._get_home_template())

        # Generate templates for each entity
        for entity in self.spec.domain.entities:
            entity_lower = entity.name.lower()
            entity_views = views_dir / entity_lower

            # List template
            (entity_views / "list.ejs").write_text(self._get_list_template(entity))

            # Detail template
            (entity_views / "detail.ejs").write_text(self._get_detail_template(entity))

            # Form template
            (entity_views / "form.ejs").write_text(self._get_form_template(entity))

            # Delete template
            (entity_views / "delete.ejs").write_text(self._get_delete_template(entity))

    def _get_layout_template(self) -> str:
        """Generate layout.ejs template."""
        app_title = self.spec.title or self.spec.name or "DAZZLE App"

        nav_links = []
        for entity in self.spec.domain.entities:
            entity_lower = entity.name.lower()
            label = entity.title or entity.name
            nav_links.append(f'        <li><a href="/{entity_lower}">{label}s</a></li>')

        # Add admin link
        if nav_links:
            nav_links.append('        <li style="border-left: 1px solid #ddd; margin-left: 10px; padding-left: 20px;"><a href="/admin">Admin</a></li>')
        else:
            nav_links.append('        <li><a href="/admin">Admin</a></li>')

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><%- title || '{app_title}' %></title>
    <link rel="stylesheet" href="/css/style.css">
</head>
<body>
    <header>
        <h1><a href="/">{app_title}</a></h1>
        <nav>
            <ul>
{chr(10).join(nav_links)}
            </ul>
        </nav>
    </header>

    <main class="container">
        <%- body %>
    </main>

    <footer style="margin-top: 50px; padding: 20px 0; border-top: 1px solid #ddd; text-align: center; color: #666;">
        <p>Generated with DAZZLE</p>
    </footer>
</body>
</html>'''

    def _get_home_template(self) -> str:
        """Generate home.ejs template."""
        app_title = self.spec.title or self.spec.name or "DAZZLE App"

        entity_cards = []
        for entity in self.spec.domain.entities:
            entity_lower = entity.name.lower()
            label = entity.title or entity.name
            entity_cards.append(f'''    <div class="card">
        <h2>{label}s</h2>
        <p>Manage {label.lower()}s in the system.</p>
        <a href="/{entity_lower}" class="btn">View {label}s</a>
        <a href="/{entity_lower}/new/form" class="btn btn-secondary">Create New</a>
    </div>''')

        # Add admin card
        admin_card = '''    <div class="card" style="border-left: 3px solid #4a90e2;">
        <h2>Admin Dashboard</h2>
        <p>Access AdminJS to manage data, configure settings, and view system information.</p>
        <a href="/admin" class="btn">Open Admin</a>
    </div>'''

        return f'''<div>
    <h2>Welcome to {app_title}</h2>

    <div style="margin-top: 30px;">
        <h3>Available Resources</h3>
{chr(10).join(entity_cards)}
    </div>

    <div style="margin-top: 40px;">
        <h3>System Tools</h3>
{admin_card}
    </div>
</div>'''

    def _get_list_template(self, entity: "ir.EntitySpec") -> str:
        """Generate list.ejs template for entity."""
        entity_lower = entity.name.lower()
        label = entity.title or entity.name

        # Get displayable fields
        display_fields = [
            f for f in entity.fields[:6]
            if f.type.kind not in [ir.FieldTypeKind.TEXT] and not f.is_primary_key
        ]

        header_cells = '\n'.join(f'            <th>{f.name.replace("_", " ").title()}</th>' for f in display_fields)
        data_cells = '\n'.join(f'            <td><%- {entity_lower}.{f.name} %></td>' for f in display_fields)

        return f'''<div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h2>{label}s</h2>
        <a href="/{entity_lower}/new/form" class="btn">Create New {label}</a>
    </div>

    <% if ({entity_lower}s && {entity_lower}s.length > 0) {{ %>
    <table>
        <thead>
        <tr>
{header_cells}
            <th>Actions</th>
        </tr>
        </thead>
        <tbody>
        <% {entity_lower}s.forEach({entity_lower} => {{ %>
        <tr>
{data_cells}
            <td>
                <a href="/{entity_lower}/<%- {entity_lower}.id %>">View</a> |
                <a href="/{entity_lower}/<%- {entity_lower}.id %>/edit">Edit</a> |
                <a href="/{entity_lower}/<%- {entity_lower}.id %>/delete">Delete</a>
            </td>
        </tr>
        <% }}); %>
        </tbody>
    </table>
    <% }} else {{ %>
    <p>No {label.lower()}s found. <a href="/{entity_lower}/new/form">Create one now</a>.</p>
    <% }} %>
</div>'''

    def _get_detail_template(self, entity: "ir.EntitySpec") -> str:
        """Generate detail.ejs template for entity."""
        entity_lower = entity.name.lower()
        label = entity.title or entity.name

        field_rows = []
        for field in entity.fields:
            if field.is_primary_key:
                continue
            field_label = field.name.replace("_", " ").title()
            field_rows.append(f'''        <tr>
            <th>{field_label}</th>
            <td><%- {entity_lower}.{field.name} %></td>
        </tr>''')

        return f'''<div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h2>{label} Detail</h2>
        <div>
            <a href="/{entity_lower}/<%- {entity_lower}.id %>/edit" class="btn">Edit</a>
            <a href="/{entity_lower}/<%- {entity_lower}.id %>/delete" class="btn btn-danger">Delete</a>
        </div>
    </div>

    <div class="card">
        <table>
{chr(10).join(field_rows)}
        </table>
    </div>

    <div style="margin-top: 20px;">
        <a href="/{entity_lower}" class="btn btn-secondary">Back to List</a>
    </div>
</div>'''

    def _get_form_template(self, entity: "ir.EntitySpec") -> str:
        """Generate form.ejs template for entity."""
        entity_lower = entity.name.lower()
        label = entity.title or entity.name

        # Generate form fields
        form_fields = []
        for field in entity.fields:
            if field.is_primary_key or ir.FieldModifier.AUTO_ADD in field.modifiers:
                continue

            field_label = field.name.replace("_", " ").title()
            input_type = self._get_html_input_type(field.type.kind)

            if field.type.kind == ir.FieldTypeKind.TEXT:
                form_fields.append(f'''        <div class="form-group">
            <label for="{field.name}">{field_label}</label>
            <textarea id="{field.name}" name="{field.name}" rows="4"><%- {entity_lower}.{field.name} || '' %></textarea>
            <% if (errors.{field.name}) {{ %>
            <div class="error"><%- errors.{field.name}.msg %></div>
            <% }} %>
        </div>''')
            else:
                form_fields.append(f'''        <div class="form-group">
            <label for="{field.name}">{field_label}</label>
            <input type="{input_type}" id="{field.name}" name="{field.name}" value="<%- {entity_lower}.{field.name} || '' %>">
            <% if (errors.{field.name}) {{ %>
            <div class="error"><%- errors.{field.name}.msg %></div>
            <% }} %>
        </div>''')

        return f'''<div>
    <h2><% if ({entity_lower}.id) {{ %>Edit<% }} else {{ %>Create<% }} %> {label}</h2>

    <form method="post" action="/<% if ({entity_lower}.id) {{ %>/{entity_lower}/<%- {entity_lower}.id %><% }} else {{ %>/{entity_lower}<% }} %>" class="card">
        <% if (errors._error) {{ %>
        <div class="alert alert-error"><%- errors._error %></div>
        <% }} %>

{chr(10).join(form_fields)}

        <div style="margin-top: 20px;">
            <button type="submit" class="btn">Save</button>
            <a href="/{entity_lower}" class="btn btn-secondary">Cancel</a>
        </div>
    </form>
</div>'''

    def _get_delete_template(self, entity: "ir.EntitySpec") -> str:
        """Generate delete.ejs template for entity."""
        entity_lower = entity.name.lower()
        label = entity.title or entity.name

        return f'''<div>
    <h2>Delete {label}</h2>

    <div class="card" style="background: #fff3cd; border-color: #ffc107;">
        <p><strong>Are you sure you want to delete this {label.lower()}?</strong></p>
        <p><%- {entity_lower}.{self._get_display_field(entity)} %></p>
        <p>This action cannot be undone.</p>

        <form method="post" action="/{entity_lower}/<%- {entity_lower}.id %>/delete">
            <button type="submit" class="btn btn-danger">Yes, Delete</button>
            <a href="/{entity_lower}/<%- {entity_lower}.id %>" class="btn btn-secondary">Cancel</a>
        </form>
    </div>
</div>'''

    def _get_html_input_type(self, field_type_kind: "ir.FieldTypeKind") -> str:
        """Map field type to HTML input type."""
        type_map = {
            ir.FieldTypeKind.STR: "text",
            ir.FieldTypeKind.INT: "number",
            ir.FieldTypeKind.DECIMAL: "number",
            ir.FieldTypeKind.BOOL: "checkbox",
            ir.FieldTypeKind.DATE: "date",
            ir.FieldTypeKind.DATETIME: "datetime-local",
            ir.FieldTypeKind.EMAIL: "email",
        }
        return type_map.get(field_type_kind, "text")

    def _get_display_field(self, entity: "ir.EntitySpec") -> str:
        """Get best field for display."""
        # Prefer: name, title, email
        priority_fields = ['name', 'title', 'email']
        for field_name in priority_fields:
            if any(f.name == field_name for f in entity.fields):
                return field_name

        # Return first non-pk field
        for field in entity.fields:
            if not field.is_primary_key:
                return field.name

        return 'id'

    def _generate_server(self) -> None:
        """Generate server.js main application file."""
        server_code = self._build_server_code()
        (self.output_dir / self.app_name / "server.js").write_text(server_code)

    def _build_server_code(self) -> str:
        """Build server.js content."""
        entity_routes = []
        for entity in self.spec.domain.entities:
            entity_lower = entity.name.lower()
            entity_routes.append(f"const {entity_lower}Routes = require('./routes/{entity_lower}');")

        entity_use = []
        for entity in self.spec.domain.entities:
            entity_lower = entity.name.lower()
            entity_use.append(f"app.use('/{entity_lower}', {entity_lower}Routes);")

        return f'''const express = require('express');
const path = require('path');
const expressLayouts = require('express-ejs-layouts');
const db = require('./models');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(express.urlencoded({{ extended: true }}));
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// View engine
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(expressLayouts);
app.set('layout', 'layout');

// Routes
const indexRoutes = require('./routes/index');
{chr(10).join(entity_routes)}

app.use('/', indexRoutes);
{chr(10).join(entity_use)}

// Database sync and server start
db.sequelize.sync().then(() => {{
  console.log('Database synced');
  app.listen(PORT, () => {{
    console.log(`Server running on http://localhost:${{PORT}}`);
    console.log(`Admin interface: http://localhost:${{PORT}}/admin`);
  }});
}}).catch(err => {{
  console.error('Database sync failed:', err);
}});

module.exports = app;
'''

    def _generate_admin(self) -> None:
        """Generate admin.js AdminJS configuration."""
        admin_code = self._build_admin_code()
        (self.output_dir / self.app_name / "admin.js").write_text(admin_code)

    def _build_admin_code(self) -> str:
        """Build admin.js content."""
        resource_configs = []
        for entity in self.spec.domain.entities:
            # Get list properties (first 5 non-pk fields)
            list_props = [f.name for f in entity.fields[:5] if not f.is_primary_key]
            list_props_str = "', '".join(list_props)

            resource_configs.append(f"""    {{
      resource: db.{entity.name},
      options: {{
        listProperties: ['{list_props_str}'],
        navigation: {{
          name: '{entity.title or entity.name}s',
          icon: 'Document'
        }}
      }}
    }}""")

        return f'''const AdminJS = require('adminjs');
const AdminJSExpress = require('@adminjs/express');
const AdminJSSequelize = require('@adminjs/sequelize');
const db = require('./models');

AdminJS.registerAdapter({{
  Database: AdminJSSequelize.Database,
  Resource: AdminJSSequelize.Resource,
}});

const adminOptions = {{
  rootPath: '/admin',
  resources: [
{(',' + chr(10)).join(resource_configs)}
  ],
  branding: {{
    companyName: '{self.spec.title or self.spec.name or "DAZZLE App"}',
    softwareBrothers: false,
  }},
}};

const adminJs = new AdminJS(adminOptions);

// Optional: Add authentication
// const adminRouter = AdminJSExpress.buildAuthenticatedRouter(adminJs, {{
//   authenticate: async (email, password) => {{
//     // Add authentication logic
//     return email === 'admin@example.com' && password === 'password';
//   }},
//   cookieName: 'adminjs',
//   cookiePassword: 'some-secret-password-used-to-secure-cookie',
// }});

const adminRouter = AdminJSExpress.buildRouter(adminJs);

module.exports = {{ adminJs, adminRouter }};
'''

    def _generate_database_config(self) -> None:
        """Generate config/database.js."""
        config_code = '''module.exports = {
  development: {
    dialect: 'sqlite',
    storage: './database.sqlite'
  },
  production: {
    dialect: 'sqlite',
    storage: './database.sqlite'
  }
};
'''
        (self.output_dir / self.app_name / "config" / "database.js").write_text(config_code)

    def _generate_package_json(self) -> None:
        """Generate package.json."""
        package_json = f'''{{
  "name": "{self.app_name}",
  "version": "1.0.0",
  "description": "Generated with DAZZLE - Express Micro Backend",
  "main": "server.js",
  "scripts": {{
    "start": "node server.js",
    "dev": "nodemon server.js",
    "init-db": "node -e \\"require('./models').sequelize.sync({{force: true}})\\""
  }},
  "dependencies": {{
    "express": "^4.18.2",
    "ejs": "^3.1.9",
    "express-ejs-layouts": "^2.5.1",
    "sequelize": "^6.35.2",
    "sqlite3": "^5.1.7",
    "express-validator": "^7.0.1",
    "adminjs": "^7.5.0",
    "@adminjs/express": "^6.1.0",
    "@adminjs/sequelize": "^4.0.0"
  }},
  "devDependencies": {{
    "nodemon": "^3.0.2"
  }},
  "engines": {{
    "node": ">=18.0.0"
  }}
}}
'''
        (self.output_dir / self.app_name / "package.json").write_text(package_json)

    def _generate_gitignore(self) -> None:
        """Generate .gitignore."""
        gitignore = '''# Dependencies
node_modules/

# Database
database.sqlite
*.sqlite
*.db

# Logs
logs/
*.log
npm-debug.log*

# Environment
.env
.env.local

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
'''
        (self.output_dir / self.app_name / ".gitignore").write_text(gitignore)

    def _generate_procfile(self) -> None:
        """Generate Procfile for Heroku."""
        procfile = 'web: node server.js\n'
        (self.output_dir / self.app_name / "Procfile").write_text(procfile)

    def _generate_vercel_config(self) -> None:
        """Generate vercel.json for Vercel deployment."""
        vercel_config = '''{
  "version": 2,
  "builds": [
    {
      "src": "server.js",
      "use": "@vercel/node"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "server.js"
    }
  ]
}
'''
        (self.output_dir / self.app_name / "vercel.json").write_text(vercel_config)

    def _generate_readme(self) -> None:
        """Generate README.md."""
        app_title = self.spec.title or self.spec.name or "DAZZLE App"

        entity_list = []
        for entity in self.spec.domain.entities:
            entity_list.append(f"- **{entity.title or entity.name}**: Manage {(entity.title or entity.name).lower()}s")

        entities_section = '\n'.join(entity_list) if entity_list else '- No entities defined'

        readme = f'''# {app_title}

Generated with [DAZZLE](https://github.com/yourusername/dazzle) - Express Micro Backend

## Overview

This is a single Express.js application using SQLite, perfect for rapid development and easy deployment.

## Features

{entities_section}

## Quick Start

### Local Development

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Initialize database**:
   ```bash
   npm run init-db
   ```

3. **Run development server**:
   ```bash
   npm run dev
   ```

4. **Access the application**:
   - Main app: http://localhost:3000/
   - Admin interface: http://localhost:3000/admin/

### Production Deployment

#### Heroku

1. **Install Heroku CLI** and login:
   ```bash
   heroku login
   ```

2. **Create Heroku app**:
   ```bash
   heroku create your-app-name
   ```

3. **Deploy**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git push heroku main
   ```

4. **Initialize database**:
   ```bash
   heroku run npm run init-db
   ```

#### Vercel

1. **Install Vercel CLI**:
   ```bash
   npm i -g vercel
   ```

2. **Deploy**:
   ```bash
   vercel
   ```

Note: Vercel deploys are stateless, so SQLite data won't persist between deployments. Consider using a hosted database for production.

#### Railway

1. **Install Railway CLI**:
   ```bash
   npm i -g @railway/cli
   ```

2. **Deploy**:
   ```bash
   railway init
   railway up
   ```

## Project Structure

```
{self.app_name}/
├── server.js              # Main application
├── package.json           # Dependencies
├── admin.js               # AdminJS configuration
├── config/
│   └── database.js        # Database configuration
├── models/                # Sequelize models
│   ├── index.js
│   └── *.js
├── routes/                # Express routes
│   ├── index.js
│   └── *.js
├── views/                 # EJS templates
│   ├── layout.ejs
│   ├── home.ejs
│   └── */
└── public/                # Static files
    └── css/
        └── style.css
```

## Admin Interface

The AdminJS interface is available at `/admin/` and provides:
- CRUD operations for all entities
- Automatic form generation
- Data filtering and search
- CSV export

## Customization

This is a standard Express.js application. You can customize:

- **Models**: Edit files in `models/`
- **Routes**: Edit files in `routes/`
- **Views**: Edit EJS templates in `views/`
- **Styles**: Edit `public/css/style.css`
- **Admin**: Edit `admin.js`

## Regeneration

To regenerate this project from the DAZZLE DSL:

```bash
dazzle build --backend express_micro --out ./build
```

Or use the express_micro stack:

```bash
dazzle build --stack express_micro --out ./build
```

## Support

- [DAZZLE Documentation](https://github.com/yourusername/dazzle)
- [Express.js Documentation](https://expressjs.com/)
- [Sequelize Documentation](https://sequelize.org/)
- [AdminJS Documentation](https://docs.adminjs.co/)

---

**Generated with DAZZLE** - Machine-first DSL for LLM-enabled apps
'''
        (self.output_dir / self.app_name / "README.md").write_text(readme)
