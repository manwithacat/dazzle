"""
React frontend adapter.

Generates TypeScript types, Zod schemas, fetch client, and
TanStack Query hooks from AppSpec.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from dazzle.stacks.base.generator import GeneratorResult
from .base import FrontendAdapter, AdapterRegistry

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec, EntitySpec, FieldSpec
    from dazzle.eject.config import EjectionFrontendConfig


class ReactAdapter(FrontendAdapter):
    """Generate React/TypeScript API layer from AppSpec."""

    # Type mappings from DSL to TypeScript
    TYPE_MAPPING = {
        "str": "string",
        "text": "string",
        "int": "number",
        "decimal": "number",
        "bool": "boolean",
        "date": "string",  # ISO date string
        "datetime": "string",  # ISO datetime string
        "uuid": "string",
        "email": "string",
        "ref": "string",  # UUID reference
        "has_many": "string[]",
        "has_one": "string | null",
        "embeds": "Record<string, unknown>",
        "belongs_to": "string",
    }

    def __init__(
        self,
        spec: "AppSpec",
        output_dir: Path,
        config: "EjectionFrontendConfig",
    ):
        super().__init__(spec, output_dir, config)
        self.frontend_dir = output_dir / "frontend"
        self.api_dir = self.frontend_dir / "src" / "api"

    def generate(self) -> GeneratorResult:
        """Generate complete frontend API layer."""
        result = GeneratorResult()

        # Create directory structure
        self._ensure_dir(self.api_dir)

        # Generate package.json
        result.merge(self._generate_package_json())

        # Generate tsconfig.json
        result.merge(self._generate_tsconfig())

        # Generate API layer
        result.merge(self.generate_types())
        result.merge(self.generate_schemas())
        result.merge(self.generate_client())
        result.merge(self.generate_hooks())
        result.merge(self.generate_validation())

        return result

    def _generate_package_json(self) -> GeneratorResult:
        """Generate package.json."""
        result = GeneratorResult()

        content = dedent(f'''
            {{
              "name": "{self.spec.name}-frontend",
              "version": "{self.spec.version}",
              "private": true,
              "type": "module",
              "scripts": {{
                "dev": "vite",
                "build": "tsc && vite build",
                "preview": "vite preview",
                "typecheck": "tsc --noEmit",
                "lint": "eslint src --ext ts,tsx",
                "test": "vitest"
              }},
              "dependencies": {{
                "react": "^18.2.0",
                "react-dom": "^18.2.0",
                "@tanstack/react-query": "^5.0.0",
                "zod": "^3.22.0"
              }},
              "devDependencies": {{
                "@types/react": "^18.2.0",
                "@types/react-dom": "^18.2.0",
                "@vitejs/plugin-react": "^4.2.0",
                "typescript": "^5.3.0",
                "vite": "^5.0.0",
                "vitest": "^1.0.0",
                "eslint": "^8.55.0",
                "@typescript-eslint/eslint-plugin": "^6.13.0",
                "@typescript-eslint/parser": "^6.13.0"
              }}
            }}
        ''').strip()

        path = self.frontend_dir / "package.json"
        self._write_file(path, content)
        result.add_file(path)

        return result

    def _generate_tsconfig(self) -> GeneratorResult:
        """Generate tsconfig.json."""
        result = GeneratorResult()

        content = dedent('''
            {
              "compilerOptions": {
                "target": "ES2020",
                "useDefineForClassFields": true,
                "lib": ["ES2020", "DOM", "DOM.Iterable"],
                "module": "ESNext",
                "skipLibCheck": true,
                "moduleResolution": "bundler",
                "allowImportingTsExtensions": true,
                "resolveJsonModule": true,
                "isolatedModules": true,
                "noEmit": true,
                "jsx": "react-jsx",
                "strict": true,
                "noUnusedLocals": true,
                "noUnusedParameters": true,
                "noFallthroughCasesInSwitch": true
              },
              "include": ["src"]
            }
        ''').strip()

        path = self.frontend_dir / "tsconfig.json"
        self._write_file(path, content)
        result.add_file(path)

        return result

    def generate_types(self) -> GeneratorResult:
        """Generate TypeScript types from entities."""
        result = GeneratorResult()

        lines = [
            "/**",
            " * TypeScript types for API entities.",
            " * Generated from DSL - DO NOT EDIT.",
            " */",
            "",
        ]

        for entity in self.spec.domain.entities:
            lines.extend(self._generate_entity_types(entity))
            lines.append("")

        content = "\n".join(lines)
        path = self.api_dir / "types.ts"
        self._write_file(path, content)
        result.add_file(path)

        return result

    def _generate_entity_types(self, entity: "EntitySpec") -> list[str]:
        """Generate TypeScript types for an entity."""
        name = entity.name
        lines = []

        # Generate enum types
        for field in entity.fields:
            if field.type.kind.value == "enum" and field.type.enum_values:
                enum_name = f"{name}{self._pascal_case(field.name)}"
                values = " | ".join(f"'{v}'" for v in field.type.enum_values)
                lines.append(f"export type {enum_name} = {values};")
                lines.append("")

        # Main interface
        if entity.intent:
            lines.append(f"/** {entity.intent} */")
        lines.append(f"export interface {name} {{")

        for field in entity.fields:
            ts_type = self._get_ts_type(field, entity)
            optional = "?" if not field.is_required and not field.is_primary_key else ""
            lines.append(f"  {field.name}{optional}: {ts_type};")

        # Add computed fields as readonly
        for cf in entity.computed_fields:
            lines.append(f"  readonly {cf.name}: string | number;  // Computed")

        lines.append("}")
        lines.append("")

        # Create type (excludes id, timestamps, computed)
        lines.append(f"export interface {name}Create {{")
        for field in entity.fields:
            if self._is_create_field(field):
                ts_type = self._get_ts_type(field, entity)
                optional = "?" if not field.is_required else ""
                lines.append(f"  {field.name}{optional}: {ts_type};")
        lines.append("}")
        lines.append("")

        # Update type (all optional)
        lines.append(f"export interface {name}Update {{")
        for field in entity.fields:
            if self._is_create_field(field):
                ts_type = self._get_ts_type(field, entity)
                lines.append(f"  {field.name}?: {ts_type};")
        lines.append("}")

        return lines

    def _is_create_field(self, field: "FieldSpec") -> bool:
        """Check if field should be in create schema."""
        if field.is_primary_key:
            return False
        if field.name in ("created_at", "updated_at"):
            return False
        if field.type.kind.value in ("has_many", "has_one", "belongs_to"):
            return False
        return True

    def _get_ts_type(self, field: "FieldSpec", entity: "EntitySpec") -> str:
        """Get TypeScript type for a field."""
        kind = field.type.kind.value

        if kind == "enum" and field.type.enum_values:
            return f"{entity.name}{self._pascal_case(field.name)}"

        ts_type = self.TYPE_MAPPING.get(kind, "unknown")

        # Handle nullability
        if not field.is_required and kind not in ("has_one",):
            ts_type = f"{ts_type} | null"

        return ts_type

    def generate_schemas(self) -> GeneratorResult:
        """Generate Zod schemas for runtime validation."""
        result = GeneratorResult()

        lines = [
            "/**",
            " * Zod schemas for runtime validation.",
            " * Generated from DSL - DO NOT EDIT.",
            " */",
            "import { z } from 'zod';",
            "",
        ]

        for entity in self.spec.domain.entities:
            lines.extend(self._generate_entity_schemas(entity))
            lines.append("")

        content = "\n".join(lines)
        path = self.api_dir / "schemas.ts"
        self._write_file(path, content)
        result.add_file(path)

        return result

    def _generate_entity_schemas(self, entity: "EntitySpec") -> list[str]:
        """Generate Zod schemas for an entity."""
        name = entity.name
        lines = []

        # Generate enum schemas
        for field in entity.fields:
            if field.type.kind.value == "enum" and field.type.enum_values:
                schema_name = f"{name}{self._pascal_case(field.name)}Schema"
                values = ", ".join(f"'{v}'" for v in field.type.enum_values)
                lines.append(f"export const {schema_name} = z.enum([{values}]);")
                lines.append("")

        # Main schema
        lines.append(f"export const {name}Schema = z.object({{")
        for field in entity.fields:
            zod_type = self._get_zod_type(field, entity)
            lines.append(f"  {field.name}: {zod_type},")
        # Add computed fields
        for cf in entity.computed_fields:
            lines.append(f"  {cf.name}: z.union([z.string(), z.number()]).optional(),")
        lines.append("});")
        lines.append("")

        # Create schema
        lines.append(f"export const {name}CreateSchema = z.object({{")
        for field in entity.fields:
            if self._is_create_field(field):
                zod_type = self._get_zod_type(field, entity, for_create=True)
                lines.append(f"  {field.name}: {zod_type},")
        lines.append("});")
        lines.append("")

        # Update schema (all optional)
        lines.append(f"export const {name}UpdateSchema = {name}CreateSchema.partial();")
        lines.append("")

        # Type exports from schemas
        lines.append(f"export type {name}Validated = z.infer<typeof {name}Schema>;")

        return lines

    def _get_zod_type(
        self,
        field: "FieldSpec",
        entity: "EntitySpec",
        for_create: bool = False,
    ) -> str:
        """Get Zod schema type for a field."""
        kind = field.type.kind.value

        # Enums
        if kind == "enum" and field.type.enum_values:
            schema_name = f"{entity.name}{self._pascal_case(field.name)}Schema"
            base = schema_name
        # Basic types
        elif kind in ("str", "text", "email"):
            max_len = field.type.max_length
            if max_len:
                base = f"z.string().max({max_len})"
            else:
                base = "z.string()"
        elif kind in ("int",):
            base = "z.number().int()"
        elif kind in ("decimal",):
            base = "z.number()"
        elif kind == "bool":
            base = "z.boolean()"
        elif kind in ("date", "datetime"):
            base = "z.string().datetime()"
        elif kind == "uuid":
            base = "z.string().uuid()"
        elif kind == "ref":
            base = "z.string().uuid()"
        else:
            base = "z.unknown()"

        # Handle optionality
        if not field.is_required:
            if for_create and field.default is not None:
                # Has default, so optional in create
                if kind == "enum":
                    default_val = f"'{field.default}'"
                elif kind == "bool":
                    default_val = str(field.default).lower()
                else:
                    default_val = repr(field.default)
                base = f"{base}.optional().default({default_val})"
            else:
                base = f"{base}.nullable().optional()"

        return base

    def generate_client(self) -> GeneratorResult:
        """Generate HTTP client with validation."""
        result = GeneratorResult()

        # Collect entity names for imports
        entity_imports = []
        entity_methods = []

        for entity in self.spec.domain.entities:
            name = entity.name
            snake = self._snake_case(name)
            entity_imports.append(f"  {name},")
            entity_imports.append(f"  {name}Create,")
            entity_imports.append(f"  {name}Update,")

            entity_methods.append(self._generate_client_methods(entity))

        imports_str = "\n".join(entity_imports)
        methods_str = "\n\n".join(entity_methods)

        content = dedent(f'''
            /**
             * HTTP client with runtime validation.
             * Generated from DSL - DO NOT EDIT.
             */
            import type {{
            {imports_str}
            }} from './types';
            import * as schemas from './schemas';

            const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

            class APIError extends Error {{
              constructor(
                message: string,
                public status: number,
                public code?: string,
              ) {{
                super(message);
                this.name = 'APIError';
              }}
            }}

            async function fetchJSON<T>(
              url: string,
              options: RequestInit = {{}},
            ): Promise<T> {{
              const response = await fetch(url, {{
                ...options,
                headers: {{
                  'Content-Type': 'application/json',
                  ...options.headers,
                }},
              }});

              if (!response.ok) {{
                const error = await response.json().catch(() => ({{}}));
                throw new APIError(
                  error.detail || 'Request failed',
                  response.status,
                  error.code,
                );
              }}

              if (response.status === 204) {{
                return undefined as T;
              }}

              return response.json();
            }}

            {methods_str}

            export const client = {{
              {", ".join(self._snake_case(e.name) + "s: " + self._snake_case(e.name) + "sClient" for e in self.spec.domain.entities)},
            }};

            export {{ APIError }};
        ''').strip()

        path = self.api_dir / "client.ts"
        self._write_file(path, content)
        result.add_file(path)

        return result

    def _generate_client_methods(self, entity: "EntitySpec") -> str:
        """Generate client methods for an entity."""
        name = entity.name
        snake = self._snake_case(name)

        return dedent(f'''
            const {snake}sClient = {{
              async list(params?: {{ skip?: number; limit?: number }}): Promise<{name}[]> {{
                const query = new URLSearchParams();
                if (params?.skip) query.set('skip', String(params.skip));
                if (params?.limit) query.set('limit', String(params.limit));
                const url = `${{API_BASE}}/{snake}s${{query.toString() ? '?' + query : ''}}`;
                const data = await fetchJSON<{name}[]>(url);
                return data.map(item => schemas.{name}Schema.parse(item));
              }},

              async get(id: string): Promise<{name}> {{
                const data = await fetchJSON<{name}>(`${{API_BASE}}/{snake}s/${{id}}`);
                return schemas.{name}Schema.parse(data);
              }},

              async create(input: {name}Create): Promise<{name}> {{
                const validated = schemas.{name}CreateSchema.parse(input);
                const data = await fetchJSON<{name}>(`${{API_BASE}}/{snake}s`, {{
                  method: 'POST',
                  body: JSON.stringify(validated),
                }});
                return schemas.{name}Schema.parse(data);
              }},

              async update(id: string, input: {name}Update): Promise<{name}> {{
                const validated = schemas.{name}UpdateSchema.parse(input);
                const data = await fetchJSON<{name}>(`${{API_BASE}}/{snake}s/${{id}}`, {{
                  method: 'PATCH',
                  body: JSON.stringify(validated),
                }});
                return schemas.{name}Schema.parse(data);
              }},

              async delete(id: string): Promise<void> {{
                await fetchJSON<void>(`${{API_BASE}}/{snake}s/${{id}}`, {{
                  method: 'DELETE',
                }});
              }},
            }}
        ''').strip()

    def generate_hooks(self) -> GeneratorResult:
        """Generate TanStack Query hooks."""
        result = GeneratorResult()

        hooks_parts = [
            "/**",
            " * TanStack Query hooks for data fetching.",
            " * Generated from DSL - DO NOT EDIT.",
            " */",
            "import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';",
            "import { client } from './client';",
            "import type {",
        ]

        for entity in self.spec.domain.entities:
            name = entity.name
            hooks_parts.append(f"  {name},")
            hooks_parts.append(f"  {name}Create,")
            hooks_parts.append(f"  {name}Update,")

        hooks_parts.append("} from './types';")
        hooks_parts.append("")

        for entity in self.spec.domain.entities:
            hooks_parts.extend(self._generate_entity_hooks(entity))
            hooks_parts.append("")

        content = "\n".join(hooks_parts)
        path = self.api_dir / "hooks.ts"
        self._write_file(path, content)
        result.add_file(path)

        return result

    def _generate_entity_hooks(self, entity: "EntitySpec") -> list[str]:
        """Generate TanStack Query hooks for an entity."""
        name = entity.name
        snake = self._snake_case(name)

        return [
            f"// === {name} Hooks ===",
            "",
            f"export const {snake}Keys = {{",
            f"  all: ['{snake}s'] as const,",
            f"  lists: () => [...{snake}Keys.all, 'list'] as const,",
            f"  list: (filters: Record<string, unknown>) => [...{snake}Keys.lists(), filters] as const,",
            f"  details: () => [...{snake}Keys.all, 'detail'] as const,",
            f"  detail: (id: string) => [...{snake}Keys.details(), id] as const,",
            "};",
            "",
            f"export function use{name}s(params?: {{ skip?: number; limit?: number }}) {{",
            "  return useQuery({",
            f"    queryKey: {snake}Keys.list(params ?? {{}}),",
            f"    queryFn: () => client.{snake}s.list(params),",
            "  });",
            "}",
            "",
            f"export function use{name}(id: string, options?: Partial<UseQueryOptions<{name}>>) {{",
            "  return useQuery({",
            f"    queryKey: {snake}Keys.detail(id),",
            f"    queryFn: () => client.{snake}s.get(id),",
            "    enabled: !!id,",
            "    ...options,",
            "  });",
            "}",
            "",
            f"export function useCreate{name}() {{",
            "  const queryClient = useQueryClient();",
            "",
            "  return useMutation({",
            f"    mutationFn: (data: {name}Create) => client.{snake}s.create(data),",
            "    onSuccess: () => {",
            f"      queryClient.invalidateQueries({{ queryKey: {snake}Keys.lists() }});",
            "    },",
            "  });",
            "}",
            "",
            f"export function useUpdate{name}() {{",
            "  const queryClient = useQueryClient();",
            "",
            "  return useMutation({",
            f"    mutationFn: ({{ id, data }}: {{ id: string; data: {name}Update }}) =>",
            f"      client.{snake}s.update(id, data),",
            "    onSuccess: (_, { id }) => {",
            f"      queryClient.invalidateQueries({{ queryKey: {snake}Keys.detail(id) }});",
            f"      queryClient.invalidateQueries({{ queryKey: {snake}Keys.lists() }});",
            "    },",
            "  });",
            "}",
            "",
            f"export function useDelete{name}() {{",
            "  const queryClient = useQueryClient();",
            "",
            "  return useMutation({",
            f"    mutationFn: (id: string) => client.{snake}s.delete(id),",
            "    onSuccess: () => {",
            f"      queryClient.invalidateQueries({{ queryKey: {snake}Keys.lists() }});",
            "    },",
            "  });",
            "}",
        ]

    def generate_validation(self) -> GeneratorResult:
        """Generate client-side invariant validators."""
        result = GeneratorResult()

        lines = [
            "/**",
            " * Client-side validation utilities.",
            " * Generated from DSL - DO NOT EDIT.",
            " */",
            "",
            "export interface ValidationError {",
            "  field: string;",
            "  message: string;",
            "  code: string;",
            "}",
            "",
            "export interface ValidationResult {",
            "  valid: boolean;",
            "  errors: ValidationError[];",
            "}",
            "",
        ]

        for entity in self.spec.domain.entities:
            if entity.invariants:
                lines.extend(self._generate_entity_validation(entity))
                lines.append("")

        content = "\n".join(lines)
        path = self.api_dir / "validation.ts"
        self._write_file(path, content)
        result.add_file(path)

        return result

    def _generate_entity_validation(self, entity: "EntitySpec") -> list[str]:
        """Generate client-side validators for an entity."""
        name = entity.name

        lines = [
            f"export function validate{name}(data: Record<string, unknown>): ValidationResult {{",
            "  const errors: ValidationError[] = [];",
            "",
        ]

        for i, inv in enumerate(entity.invariants):
            message = inv.message or "Validation failed"
            code = inv.code or f"{name.upper()}_INVARIANT_{i}"
            lines.append(f"  // Invariant {i + 1}")
            lines.append(f"  // TODO: Implement client-side check for: {code}")
            lines.append("")

        lines.extend([
            "  return {",
            "    valid: errors.length === 0,",
            "    errors,",
            "  };",
            "}",
        ])

        return lines

    # Utility methods

    def _snake_case(self, name: str) -> str:
        """Convert PascalCase to snake_case."""
        result = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())
        return "".join(result)

    def _pascal_case(self, name: str) -> str:
        """Convert snake_case to PascalCase."""
        return "".join(word.capitalize() for word in name.split("_"))


# Register adapter
AdapterRegistry.register_frontend("react", ReactAdapter)
