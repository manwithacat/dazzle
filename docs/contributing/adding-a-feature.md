# Adding a Feature

Guide to extending Dazzle with new functionality.

## Types of Features

| Type | Where | Example |
|------|-------|---------|
| DSL construct | `src/dazzle/core/` | New entity modifier |
| CLI command | `src/dazzle/cli/` | New subcommand |
| Backend capability | `src/dazzle_back/` | New API pattern |
| UI component | `src/dazzle_ui/` | New widget |
| Code generator | `src/dazzle/eject/` | New ejection target |

## Adding a DSL Construct

### 1. Update the Grammar

Edit `docs/v0.9/DAZZLE_DSL_GRAMMAR.ebnf`:

```ebnf
my_construct = "my_keyword", identifier, ":", block ;
```

### 2. Add IR Types

Create or update types in `src/dazzle/core/ir/`:

```python
# src/dazzle/core/ir/my_construct.py
from pydantic import BaseModel

class MyConstructSpec(BaseModel):
    name: str
    value: str
```

### 3. Update Parser

Add parsing logic in `src/dazzle/core/dsl_parser.py`:

```python
def parse_my_construct(self, tokens: list[Token]) -> MyConstructSpec:
    # Parse tokens into spec
    pass
```

### 4. Add Validation

Add validation in `src/dazzle/core/validator.py`:

```python
def validate_my_construct(self, spec: MyConstructSpec) -> list[Error]:
    errors = []
    if not spec.name:
        errors.append(Error("Name required"))
    return errors
```

### 5. Add Tests

Create `tests/unit/test_my_construct.py`:

```python
import pytest
from dazzle.core.dsl_parser import parse_dsl

class TestMyConstruct:
    def test_basic_parsing(self):
        result = parse_dsl("""
            my_keyword foo:
                value: bar
        """)
        assert result.my_constructs[0].name == "foo"
```

### 6. Update Documentation

Add to `docs/reference/`:

```markdown
# My Construct

Description and usage examples.

## Syntax

\`\`\`dsl
my_keyword name:
    value: something
\`\`\`
```

## Adding a CLI Command

### 1. Create Command Module

Create `src/dazzle/cli/commands/my_command.py`:

```python
import click

@click.command()
@click.argument('name')
def my_command(name: str):
    """Description of my command."""
    click.echo(f"Hello {name}")
```

### 2. Register Command

Add to `src/dazzle/cli/main.py`:

```python
from dazzle.cli.commands.my_command import my_command

cli.add_command(my_command)
```

### 3. Add Tests

Create `tests/unit/test_cli_my_command.py`:

```python
from click.testing import CliRunner
from dazzle.cli.main import cli

def test_my_command():
    runner = CliRunner()
    result = runner.invoke(cli, ['my-command', 'world'])
    assert result.exit_code == 0
    assert 'Hello world' in result.output
```

## Adding a Backend Capability

### 1. Define Service

Add to `src/dazzle_back/services/`:

```python
class MyService:
    async def my_method(self, data: dict) -> dict:
        # Implementation
        return {"result": "success"}
```

### 2. Add Route

Add to `src/dazzle_back/routes/`:

```python
@router.post("/my-endpoint")
async def my_endpoint(data: MyRequest) -> MyResponse:
    return await my_service.my_method(data)
```

### 3. Add Tests

Create `src/dazzle_back/tests/test_my_service.py`:

```python
import pytest

@pytest.mark.asyncio
async def test_my_method():
    service = MyService()
    result = await service.my_method({})
    assert result["result"] == "success"
```

## Adding a UI Component

### 1. Create Component

Add to `src/dazzle_ui/runtime/static/js/components/`:

```javascript
// @ts-check

/**
 * @param {Object} props
 * @param {string} props.label
 * @returns {HTMLElement}
 */
export function MyComponent(props) {
    const el = document.createElement('div');
    el.textContent = props.label;
    return el;
}
```

### 2. Register Component

Add to `src/dazzle_ui/runtime/static/js/components.js`:

```javascript
import { MyComponent } from './components/my-component.js';

registry.register('MyComponent', MyComponent);
```

### 3. Add Tests

Create `src/dazzle_ui/runtime/static/js/my-component.test.js`:

```javascript
import { describe, it, expect } from 'vitest';
import { MyComponent } from './components/my-component.js';

describe('MyComponent', () => {
    it('renders label', () => {
        const el = MyComponent({ label: 'Hello' });
        expect(el.textContent).toBe('Hello');
    });
});
```

## Checklist

Before submitting a PR:

- [ ] Tests pass: `pytest tests/unit -x`
- [ ] Types check: `mypy src/dazzle`
- [ ] Lints pass: `ruff check src/`
- [ ] JavaScript tests: `npm test`
- [ ] Documentation updated
- [ ] Example added (if applicable)

## See Also

- [Development Setup](dev-setup.md)
- [Testing Guide](testing.md)
