"""
Forms generator for Django Micro backend.

Generates Django forms.py with surface-specific forms.
"""

from pathlib import Path
from typing import Optional

from ...base import Generator, GeneratorResult
from ....core import ir


class FormsGenerator(Generator):
    """
    Generate Django forms from entities and surfaces.

    Creates forms.py with:
    - Surface-specific forms (CreateForm, EditForm)
    - Field inclusion based on surface definition
    - ModelForm configuration
    """

    def __init__(self, spec: ir.AppSpec, output_dir: Path, app_name: str = "app"):
        """
        Initialize forms generator.

        Args:
            spec: Application specification
            output_dir: Root output directory
            app_name: Name of the Django app
        """
        super().__init__(spec, output_dir)
        self.app_name = app_name

    def generate(self) -> GeneratorResult:
        """Generate forms.py file."""
        result = GeneratorResult()

        # Build forms code
        code = self._build_forms_code()

        # Write file
        forms_path = self.output_dir / self.app_name / "forms.py"
        self._write_file(forms_path, code)
        result.add_file(forms_path)

        # Record form names for other generators
        form_names = []
        for entity in self.spec.domain.entities:
            # Find surfaces for this entity
            create_surface = self._find_surface_for_entity(entity.name, ir.SurfaceMode.CREATE)
            edit_surface = self._find_surface_for_entity(entity.name, ir.SurfaceMode.EDIT)

            if create_surface:
                form_names.append(f'{entity.name}CreateForm')
            if edit_surface:
                form_names.append(f'{entity.name}Form')

        result.add_artifact("form_names", form_names)

        return result

    def _build_forms_code(self) -> str:
        """Build complete forms.py content."""
        lines = [
            '"""',
            'Django forms generated from DAZZLE DSL.',
            '"""',
            'from django import forms',
            'from .models import (',
        ]

        # Import models
        for entity in self.spec.domain.entities:
            lines.append(f'    {entity.name},')
        lines.append(')')
        lines.append('')
        lines.append('')

        # Generate forms for each entity
        for entity in self.spec.domain.entities:
            # Find surfaces for this entity
            create_surface = self._find_surface_for_entity(entity.name, ir.SurfaceMode.CREATE)
            edit_surface = self._find_surface_for_entity(entity.name, ir.SurfaceMode.EDIT)

            # Generate create form if create surface exists
            if create_surface:
                lines.append(self._generate_surface_form(entity, create_surface,
                                                         f'{entity.name}CreateForm', 'creation'))
                lines.append('')
                lines.append('')

            # Generate edit form if edit surface exists or as fallback
            if edit_surface:
                lines.append(self._generate_surface_form(entity, edit_surface,
                                                         f'{entity.name}Form', 'editing'))
            else:
                # Fallback: generate a generic edit form if no edit surface
                lines.append(self._generate_generic_form(entity, f'{entity.name}Form'))

            lines.append('')
            lines.append('')

        return '\n'.join(lines)

    def _generate_surface_form(self, entity: ir.EntitySpec, surface: ir.SurfaceSpec,
                               form_class_name: str, purpose: str) -> str:
        """Generate a form class based on a surface definition."""
        lines = [
            f'class {form_class_name}(forms.ModelForm):',
            f'    """{entity.name} form for {purpose}."""',
            '',
            '    class Meta:',
            f'        model = {entity.name}',
        ]

        # Get fields to include from surface
        included_fields = self._get_surface_fields(entity, surface)

        if included_fields:
            fields_str = ', '.join(f'"{f}"' for f in included_fields)
            # Add trailing comma for single-field tuples
            if len(included_fields) == 1:
                lines.append(f'        fields = ({fields_str},)')
            else:
                lines.append(f'        fields = ({fields_str})')
        else:
            lines.append('        fields = "__all__"')

        # Add widgets for better UX
        widgets = self._get_form_widgets(entity, included_fields)
        if widgets:
            lines.append('        widgets = {')
            for field_name, widget in widgets.items():
                lines.append(f'            "{field_name}": {widget},')
            lines.append('        }')

        return '\n'.join(lines)

    def _generate_generic_form(self, entity: ir.EntitySpec, form_class_name: str) -> str:
        """Generate a generic form (no surface definition)."""
        lines = [
            f'class {form_class_name}(forms.ModelForm):',
            f'    """{entity.name} form."""',
            '',
            '    class Meta:',
            f'        model = {entity.name}',
            '        fields = "__all__"',
        ]

        return '\n'.join(lines)

    def _get_surface_fields(self, entity: ir.EntitySpec, surface: ir.SurfaceSpec) -> list:
        """Get list of fields to include in form based on surface definition."""
        included_fields = []

        # Extract fields from surface sections
        if surface.sections:
            for section in surface.sections:
                for element in section.elements:
                    if element.field_name:
                        # Find matching entity field
                        entity_field = next((f for f in entity.fields if f.name == element.field_name), None)
                        if entity_field:
                            # Exclude auto-generated fields (can't be edited)
                            if not (ir.FieldModifier.AUTO_ADD in entity_field.modifiers or
                                   ir.FieldModifier.AUTO_UPDATE in entity_field.modifiers):
                                if element.field_name not in included_fields:
                                    included_fields.append(element.field_name)
        else:
            # Include all non-auto fields
            for field in entity.fields:
                if not (ir.FieldModifier.AUTO_ADD in field.modifiers or
                       ir.FieldModifier.AUTO_UPDATE in field.modifiers):
                    included_fields.append(field.name)

        return included_fields

    def _get_form_widgets(self, entity: ir.EntitySpec, included_fields: list) -> dict:
        """Get custom widgets for form fields."""
        widgets = {}

        for field in entity.fields:
            if field.name not in included_fields:
                continue

            # Text fields get textarea widget
            if field.type.kind == ir.FieldTypeKind.TEXT:
                widgets[field.name] = 'forms.Textarea(attrs={"rows": 4})'

            # Email fields get email input
            elif field.type.kind == ir.FieldTypeKind.EMAIL:
                widgets[field.name] = 'forms.EmailInput(attrs={"class": "form-control"})'

            # Date fields get date input
            elif field.type.kind == ir.FieldTypeKind.DATE:
                widgets[field.name] = 'forms.DateInput(attrs={"type": "date"})'

            # DateTime fields get datetime-local input
            elif field.type.kind == ir.FieldTypeKind.DATETIME:
                widgets[field.name] = 'forms.DateTimeInput(attrs={"type": "datetime-local"})'

        return widgets

    def _find_surface_for_entity(self, entity_name: str, mode: ir.SurfaceMode) -> Optional[ir.SurfaceSpec]:
        """Find surface for an entity with specific mode."""
        for surface in self.spec.surfaces:
            if surface.entity_ref == entity_name and surface.mode == mode:
                return surface
        return None
