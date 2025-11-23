"""
Views generator for Django Micro backend.

Generates Django views.py with class-based views from surfaces.
"""

from pathlib import Path
from typing import Optional

from ...base import Generator, GeneratorResult
from ....core import ir


class ViewsGenerator(Generator):
    """
    Generate Django views from surfaces.

    Creates views.py with:
    - Class-based views (ListView, DetailView, CreateView, UpdateView, DeleteView)
    - View classes mapped to surfaces
    - Form class selection based on surface mode
    - Success URLs and redirects
    """

    def __init__(self, spec: ir.AppSpec, output_dir: Path, app_name: str = "app"):
        """
        Initialize views generator.

        Args:
            spec: Application specification
            output_dir: Root output directory
            app_name: Name of the Django app
        """
        super().__init__(spec, output_dir)
        self.app_name = app_name

    def generate(self) -> GeneratorResult:
        """Generate views.py file."""
        result = GeneratorResult()

        # Build views code
        code = self._build_views_code()

        # Write file
        views_path = self.output_dir / self.app_name / "views.py"
        self._write_file(views_path, code)
        result.add_file(views_path)

        # Record view names for URL configuration
        view_names = []
        for surface in self.spec.surfaces:
            if surface.entity_ref:
                view_class_name = self._get_view_class_name(surface, surface.entity_ref)
                view_names.append(view_class_name)

        result.add_artifact("view_names", view_names)

        return result

    def _build_views_code(self) -> str:
        """Build complete views.py content."""
        lines = [
            '"""',
            'Django views generated from DAZZLE DSL.',
            '"""',
            'from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView',
            'from django.urls import reverse_lazy',
            'from .models import (',
        ]

        # Import models
        for entity in self.spec.domain.entities:
            lines.append(f'    {entity.name},')
        lines.append(')')

        # Import forms
        lines.append('from .forms import (')
        for entity in self.spec.domain.entities:
            # Check which forms exist
            create_surface = self._find_surface_for_entity(entity.name, ir.SurfaceMode.CREATE)
            edit_surface = self._find_surface_for_entity(entity.name, ir.SurfaceMode.EDIT)

            if create_surface:
                lines.append(f'    {entity.name}CreateForm,')
            if edit_surface:
                lines.append(f'    {entity.name}Form,')
        lines.append(')')
        lines.append('')
        lines.append('')

        # Generate home view
        lines.append(self._generate_home_view())
        lines.append('')
        lines.append('')

        # Generate views for each surface
        generated_entities = set()
        for surface in self.spec.surfaces:
            if surface.entity_ref:
                lines.append(self._generate_view_for_surface(surface))
                lines.append('')
                lines.append('')
                generated_entities.add(surface.entity_ref)

        # Generate DeleteView for each entity (not surface-specific)
        for entity in self.spec.domain.entities:
            if entity.name in generated_entities:
                entity_lower = entity.name.lower()
                lines.append(self._generate_delete_view(entity, entity_lower))
                lines.append('')
                lines.append('')

        return '\n'.join(lines)

    def _generate_home_view(self) -> str:
        """Generate home page view."""
        lines = [
            'from django.views.generic import TemplateView',
            '',
            '',
            'class HomeView(TemplateView):',
            '    """Home page view."""',
            '    template_name = "app/home.html"',
            '',
            '    def get_context_data(self, **kwargs):',
            '        context = super().get_context_data(**kwargs)',
            '        # Add any home page context here',
            '        return context',
        ]
        return '\n'.join(lines)

    def _generate_view_for_surface(self, surface: ir.SurfaceSpec) -> str:
        """Generate view class for a surface."""
        entity_name = surface.entity_ref
        view_class_name = self._get_view_class_name(surface, entity_name)

        # Map surface mode to Django view type
        if surface.mode == ir.SurfaceMode.LIST:
            return self._generate_list_view(surface, entity_name, view_class_name)
        elif surface.mode == ir.SurfaceMode.VIEW:
            return self._generate_detail_view(surface, entity_name, view_class_name)
        elif surface.mode == ir.SurfaceMode.CREATE:
            return self._generate_create_view(surface, entity_name, view_class_name)
        elif surface.mode == ir.SurfaceMode.EDIT:
            return self._generate_update_view(surface, entity_name, view_class_name)
        else:
            # Default to TemplateView for custom surfaces
            return self._generate_template_view(surface, view_class_name)

    def _generate_list_view(self, surface: ir.SurfaceSpec, entity_name: str, view_class_name: str) -> str:
        """Generate ListView for list surface."""
        entity_lower = entity_name.lower()
        lines = [
            f'class {view_class_name}(ListView):',
            f'    """{surface.title or surface.name} view."""',
            f'    model = {entity_name}',
            f'    template_name = "app/{entity_lower}_list.html"',
            f'    context_object_name = "{entity_lower}s"',
            '    paginate_by = 50',
            '',
            '    def get_queryset(self):',
            '        """Get filtered queryset."""',
            '        queryset = super().get_queryset()',
            '        # Add any filtering here',
            '        return queryset',
        ]
        return '\n'.join(lines)

    def _generate_detail_view(self, surface: ir.SurfaceSpec, entity_name: str, view_class_name: str) -> str:
        """Generate DetailView for view surface."""
        entity_lower = entity_name.lower()
        lines = [
            f'class {view_class_name}(DetailView):',
            f'    """{surface.title or surface.name} view."""',
            f'    model = {entity_name}',
            f'    template_name = "app/{entity_lower}_detail.html"',
            f'    context_object_name = "{entity_lower}"',
        ]
        return '\n'.join(lines)

    def _generate_create_view(self, surface: ir.SurfaceSpec, entity_name: str, view_class_name: str) -> str:
        """Generate CreateView for create surface."""
        entity_lower = entity_name.lower()
        lines = [
            f'class {view_class_name}(CreateView):',
            f'    """{surface.title or surface.name} view."""',
            f'    model = {entity_name}',
            f'    form_class = {entity_name}CreateForm',
            f'    template_name = "app/{entity_lower}_form.html"',
            f'    success_url = reverse_lazy("{entity_lower}-list")',
        ]

        # Check for required foreign keys not in form (need auto-population)
        entity = self._get_entity_by_name(entity_name)
        if entity:
            missing_required_fks = self._get_missing_required_foreign_keys(entity, surface)

            if missing_required_fks:
                lines.append('')
                lines.append('    def form_valid(self, form):')
                lines.append('        """Handle successful form submission."""')

                for fk_field in missing_required_fks:
                    ref_entity = fk_field.type.ref_entity
                    lines.append(f'        # Auto-populate {fk_field.name} (required but not in form)')
                    lines.append(f'        # NOTE: Customize this logic based on your authentication requirements')
                    lines.append(f'        if not form.instance.{fk_field.name}_id:')
                    lines.append(f'            form.instance.{fk_field.name} = {ref_entity}.objects.first()')
                    lines.append(f'            if not form.instance.{fk_field.name}:')
                    lines.append(f'                # Create default {ref_entity} if none exists')

                    # Generate sensible default values based on entity fields
                    default_values = self._get_default_values_for_entity(ref_entity)
                    lines.append(f'                form.instance.{fk_field.name} = {ref_entity}.objects.create(')
                    for field_name, field_value in default_values.items():
                        lines.append(f'                    {field_name}={field_value},')
                    lines.append('                )')
                    lines.append('')

                lines.append('        response = super().form_valid(form)')
                lines.append('        return response')
            else:
                # No missing required FKs, use simple form_valid
                lines.append('')
                lines.append('    def form_valid(self, form):')
                lines.append('        """Handle successful form submission."""')
                lines.append('        response = super().form_valid(form)')
                lines.append('        # Add success message here')
                lines.append('        return response')

        return '\n'.join(lines)

    def _generate_update_view(self, surface: ir.SurfaceSpec, entity_name: str, view_class_name: str) -> str:
        """Generate UpdateView for edit surface."""
        entity_lower = entity_name.lower()
        # Use standard naming: EntityUpdateView instead of EntityEditView
        update_view_name = f'{entity_name}UpdateView'
        lines = [
            f'class {update_view_name}(UpdateView):',
            f'    """{surface.title or surface.name} view."""',
            f'    model = {entity_name}',
            f'    form_class = {entity_name}Form',
            f'    template_name = "app/{entity_lower}_form.html"',
            f'    success_url = reverse_lazy("{entity_lower}-list")',
            '',
            '    def form_valid(self, form):',
            '        """Handle successful form submission."""',
            '        response = super().form_valid(form)',
            '        # Add success message here',
            '        return response',
        ]
        return '\n'.join(lines)

    def _generate_template_view(self, surface: ir.SurfaceSpec, view_class_name: str) -> str:
        """Generate TemplateView for custom surface."""
        template_name = surface.name.lower().replace('_', '-')
        lines = [
            f'class {view_class_name}(TemplateView):',
            f'    """{surface.title or surface.name} view."""',
            f'    template_name = "app/{template_name}.html"',
        ]
        return '\n'.join(lines)

    def _generate_delete_view(self, entity: ir.EntitySpec, entity_lower: str) -> str:
        """Generate DeleteView for entity."""
        entity_name = entity.name
        lines = [
            f'class {entity_name}DeleteView(DeleteView):',
            f'    """Delete {entity.title or entity_name} view."""',
            f'    model = {entity_name}',
            f'    template_name = "app/{entity_lower}_confirm_delete.html"',
            f'    success_url = reverse_lazy("{entity_lower}-list")',
        ]
        return '\n'.join(lines)

    def _get_view_class_name(self, surface: ir.SurfaceSpec, entity_name: str) -> str:
        """
        Get Django view class name for a surface.

        Uses entity name + mode to ensure consistent naming.
        Example: MaintenanceTask + list -> MaintenanceTaskListView
        """
        # Map surface mode to view suffix
        mode_suffix_map = {
            ir.SurfaceMode.LIST: 'List',
            ir.SurfaceMode.VIEW: 'Detail',
            ir.SurfaceMode.CREATE: 'Create',
            ir.SurfaceMode.EDIT: 'Update',
        }

        # Get the suffix for this mode
        suffix = mode_suffix_map.get(surface.mode, '')

        # Build class name: EntityName + Suffix + View
        # Example: MaintenanceTask + List + View = MaintenanceTaskListView
        if suffix:
            class_name = f'{entity_name}{suffix}View'
        else:
            # For custom modes, use surface name as fallback
            parts = surface.name.split('_')
            class_name = ''.join(word.capitalize() for word in parts)
            if not class_name.endswith('View'):
                class_name += 'View'

        return class_name

    def _find_surface_for_entity(self, entity_name: str, mode: ir.SurfaceMode) -> Optional[ir.SurfaceSpec]:
        """Find surface for an entity with specific mode."""
        for surface in self.spec.surfaces:
            if surface.entity_ref == entity_name and surface.mode == mode:
                return surface
        return None

    def _get_entity_by_name(self, entity_name: str) -> Optional[ir.EntitySpec]:
        """Get entity spec by name."""
        for entity in self.spec.domain.entities:
            if entity.name == entity_name:
                return entity
        return None

    def _get_missing_required_foreign_keys(self, entity: ir.EntitySpec, surface: ir.SurfaceSpec) -> list:
        """
        Find required foreign key fields that are missing from the form.

        These need to be auto-populated in the view's form_valid method.
        """
        missing_fks = []

        # Get fields included in the surface
        included_field_names = set()
        if surface.sections:
            for section in surface.sections:
                for element in section.elements:
                    if element.field_name:
                        included_field_names.add(element.field_name)

        # Find required foreign keys not in the form
        for field in entity.fields:
            # Check if it's a required foreign key
            if (field.type.kind == ir.FieldTypeKind.REF and
                field.is_required and
                field.name not in included_field_names and
                not field.is_primary_key):
                missing_fks.append(field)

        return missing_fks

    def _get_default_values_for_entity(self, entity_name: str) -> dict:
        """
        Generate sensible default values for creating a default entity instance.

        Returns a dict of field_name: value pairs for required fields.
        """
        entity = self._get_entity_by_name(entity_name)
        if not entity:
            return {}

        defaults = {}

        for field in entity.fields:
            # Skip auto-generated fields and foreign keys
            if (field.is_primary_key or
                ir.FieldModifier.AUTO_ADD in field.modifiers or
                ir.FieldModifier.AUTO_UPDATE in field.modifiers or
                field.type.kind == ir.FieldTypeKind.REF):
                continue

            # Only include required fields
            if not field.is_required:
                continue

            # Generate default based on field type
            field_name = field.name
            field_type = field.type.kind

            if field_type == ir.FieldTypeKind.EMAIL:
                defaults[field_name] = f'"system@example.com"'
            elif field_type == ir.FieldTypeKind.STR:
                # Use field name as hint for default value
                if 'name' in field_name.lower():
                    defaults[field_name] = f'"System {entity_name}"'
                else:
                    defaults[field_name] = f'"{field_name.replace("_", " ").title()}"'
            elif field_type == ir.FieldTypeKind.TEXT:
                defaults[field_name] = f'"Auto-generated default {entity_name.lower()}"'
            elif field_type == ir.FieldTypeKind.BOOL:
                defaults[field_name] = 'True'
            elif field_type == ir.FieldTypeKind.INT:
                defaults[field_name] = '0'
            elif field_type == ir.FieldTypeKind.DECIMAL:
                defaults[field_name] = '0.0'
            elif field_type == ir.FieldTypeKind.ENUM:
                # Use first enum value as default
                if field.type.enum_values:
                    defaults[field_name] = f'"{field.type.enum_values[0]}"'

        return defaults
