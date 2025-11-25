# Dazzle Project Instructions for Claude

This is a Dazzle project for generating full-stack applications from DSL specifications.

## Important Notes

### API Keys are OPTIONAL
- The `dazzle analyze-spec` command can use AI to convert natural language to DSL
- **This is completely optional** - you can write DSL directly without any API keys
- Users control and pay for their own AI tokens if they choose to use this feature
- Claude (you) should help users write DSL directly when they don't have API keys

## Your Primary Tasks

1. **Help write DSL specifications** in the `dsl/` directory
2. **Validate DSL** using `dazzle validate`
3. **Build applications** using `dazzle build --stack [stackname]`
4. **Fix validation errors** by editing `.dsl` files
5. **Answer questions** about Dazzle DSL syntax and capabilities

## Project Structure

```
.
├── dazzle.toml         # Project configuration
├── SPEC.md             # Natural language requirements (optional)
├── dsl/                # DSL specification files
│   └── *.dsl          # Your domain models and UI definitions
└── build/              # Generated code (after dazzle build)
```

## Common Workflows

### Creating DSL from Requirements
If the user has requirements in SPEC.md or describes them to you:
1. Help them write DSL directly - no API keys needed
2. Create entities, surfaces, and other constructs in `.dsl` files
3. Validate with `dazzle validate`
4. Build with `dazzle build`

### Working with Existing DSL
1. Read existing `.dsl` files in the `dsl/` directory
2. Make modifications as requested
3. Always validate after changes
4. Build when ready

### Available Stacks
Use `dazzle stacks` to see available code generation targets:
- `micro` or `django_micro_modular` - Full Django app with UI
- `django_api` - Django REST API
- `express_micro` - Node.js/Express app
- `openapi` - OpenAPI specification
- `docker` - Docker Compose setup
- `terraform` - AWS infrastructure

## DSL Quick Reference

### Basic Entity
```dsl
module myapp.core

entity User "User":
  id: uuid pk
  email: str(200) unique required
  name: str(100) required
  created_at: datetime auto_add
```

### Surface (UI)
```dsl
surface user_list "Users":
  uses entity User
  mode: list

surface user_form "User Form":
  uses entity User
  mode: form
```

### Field Types
- `uuid`, `str(n)`, `text`, `int`, `float`, `bool`
- `datetime`, `date`, `time`
- `enum[option1,option2,option3]`
- `ref OtherEntity` (relationships)

### Modifiers
- `pk` - Primary key
- `required` - Not nullable
- `unique` - Unique constraint
- `auto_add` - Set on creation
- `auto_update` - Update on save

## Important Reminders

1. **Always validate before building** - `dazzle validate` first
2. **Check the dsl/ directory** - DSL files go here, not in root
3. **API keys are optional** - You can write DSL without them
4. **Users pay for their own tokens** - If they choose to use AI features
5. **The .clinerules file** - Pre-approves common commands to reduce friction

## When Users Ask About Costs

If users ask about API costs or tokens:
- Explain that Dazzle can be used **completely free** without AI
- They can write DSL directly (with your help)
- The AI features are optional conveniences
- If they have their own API keys, they control their spending

## Your Capabilities

You can:
- ✅ Write and modify DSL files
- ✅ Run dazzle commands (validate, build, lint, etc.)
- ✅ Read and explain generated code
- ✅ Debug validation errors
- ✅ Suggest DSL patterns and best practices

You should NOT:
- ❌ Require users to get API keys
- ❌ Assume AI features are necessary
- ❌ Modify generated code directly (regenerate instead)
- ❌ Create files outside the DSL structure without user request

Remember: Your primary role is to help users create applications using Dazzle DSL, with or without AI assistance.
