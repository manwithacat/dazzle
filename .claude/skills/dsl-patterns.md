---
auto_load: true
globs:
  - "**/*.dazzle"
  - "**/dsl_parser*.py"
  - "**/ir/**/*.py"
---

# DSL Patterns & Gotchas

## Syntax Rules

- **Strings**: Always use double quotes `"like this"`, never single quotes
- **Identifiers**: Must start with a letter, can contain `_` and digits. Use `snake_case` for field names, `PascalCase` for entity/surface names
- **Indentation**: 2-space indent for block contents. Consistent within a block
- **Comments**: `// line comment` or `/* block comment */`

## Common Mistakes

1. **Missing `required` on entity fields** — `id: uuid pk` implicitly required, but other fields need explicit `required`
2. **Forgetting `uses entity X`** on surfaces — every surface must declare which entity it uses
3. **Enum syntax** — `status: enum[draft, active, archived]` not `enum(draft, active, archived)`
4. **Ref syntax** — `owner: ref User` not `ref(User)` or `User`
5. **String length** — `title: str(200)` not `str[200]` or `string(200)`
6. **Boolean defaults** — `completed: bool=false` not `bool=False` (lowercase)
7. **PersonaSpec** uses `.id` not `.name` — use `getattr(p, "name", None) or getattr(p, "id", "unknown")`
8. **State machine states** are plain strings, not objects — use `s if isinstance(s, str) else s.name`

## Field Types

| DSL Type | IR Type | Notes |
|----------|---------|-------|
| `uuid` | `ScalarType.UUID` | Primary keys |
| `str(N)` | `ScalarType.STR` | N = max length |
| `text` | `ScalarType.TEXT` | Unlimited text |
| `int` | `ScalarType.INT` | Integer |
| `float` | `ScalarType.FLOAT` | Decimal |
| `bool` | `ScalarType.BOOL` | true/false |
| `date` | `ScalarType.DATE` | Date only |
| `datetime` | `ScalarType.DATETIME` | Date + time |
| `money` | `ScalarType.MONEY` | Currency amount |
| `json` | `ScalarType.JSON` | JSON blob |
| `enum[a,b,c]` | `EnumType` | Enumeration |
| `ref Entity` | `RefType` | Foreign key |
| `list ref Entity` | `ListRefType` | Many-to-many |

## Construct Reference

All top-level constructs: `entity`, `surface`, `workspace`, `experience`, `service`, `foreign_model`, `integration`, `ledger`, `transaction`, `process`, `schedule`, `story`, `archetype`, `persona`, `scenario`

## Parser Extension Checklist

When adding a new DSL construct:
1. Grammar in `docs/reference/grammar.md`
2. IR types in `src/dazzle/core/ir/`
3. Parser mixin in `src/dazzle/core/dsl_parser_impl/`
4. Tests in `tests/unit/test_parser.py`
