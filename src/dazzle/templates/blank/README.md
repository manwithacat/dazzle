# {{project_title}}

A DAZZLE project generated with `dazzle init`.

## Getting Started

1. **Define your domain model** in `dsl/app.dsl`:
   - Add entities (data models)
   - Define surfaces (UI screens/views)
   - Create services (integrations)
   - Design experiences (workflows)

2. **Validate your spec**:
   ```bash
   dazzle validate
   ```

3. **Generate artifacts**:
   ```bash
   dazzle build --backend openapi --out ./build
   ```

4. **List available backends**:
   ```bash
   dazzle backends
   ```

## Project Structure

```
{{project_name}}/
├── dazzle.toml          # Project manifest
├── dsl/                 # DSL module files
│   └── app.dsl          # Main application spec
└── build/               # Generated artifacts (created after dazzle build)
```

## Resources

- [DAZZLE Documentation](https://github.com/manwithacat/dazzle)
- [DSL Reference](https://github.com/manwithacat/dazzle/blob/main/docs)
- [Examples](https://github.com/manwithacat/dazzle/tree/main/examples)
