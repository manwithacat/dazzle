# Custom Stacks

> **Note**: For most use cases, use the Dazzle Native Runtime (DNR) which runs DSL directly without code generation. Custom stacks are for specialized deployment requirements.

## Overview

DAZZLE provides a `base` builder for creating custom code generation stacks when you need to:

- Generate code for a specific framework not supported by DNR
- Create deployable artifacts for environments without Python
- Integrate with existing build pipelines

## Quick Example

```python
from dazzle.stacks.base import BaseBackend

class MyStack(BaseBackend):
    """Custom stack for generating Flask applications."""

    def generate(self, appspec, output_dir, artifacts=None):
        # Transform AppSpec into your target format
        for entity in appspec.domain.entities:
            self._generate_model(entity, output_dir)

        for surface in appspec.surfaces:
            self._generate_view(surface, output_dir)

    def _generate_model(self, entity, output_dir):
        # Generate entity model code
        ...

    def _generate_view(self, surface, output_dir):
        # Generate surface view code
        ...
```

## Registration

Register your stack in `pyproject.toml`:

```toml
[project.entry-points."dazzle.stacks"]
mystack = "mypackage.stack:MyStack"
```

Then use it:

```bash
dazzle build --stack mystack
```

## Available Stacks

| Stack | Status | Description |
|-------|--------|-------------|
| `base` | Available | Base builder for custom stacks |
| `docker` | In Progress | Docker Compose for DNR apps |

Legacy stacks (`django_micro_modular`, `express_micro`, `nextjs_semantic`) are deprecated.

## Recommended Approach

1. **Start with DNR** - Use `dazzle dnr serve` for development
2. **Use Docker stack** - For containerized deployment (coming soon)
3. **Build custom stack** - Only if you have specific requirements

## Resources

- [DNR Architecture](dnr/ARCHITECTURE.md)
- [Base Builder Source](../src/dazzle/stacks/base/)
- [AppSpec IR Reference](v0.1/DAZZLE_IR.md)
