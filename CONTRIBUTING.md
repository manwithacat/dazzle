# Contributing to DAZZLE

Thank you for your interest in contributing to DAZZLE! We're excited to have you here. Whether you're fixing a bug, adding a feature, improving documentation, or just sharing ideas, your contributions make DAZZLE better for everyone.

## 🌟 Ways to Contribute

We welcome all kinds of contributions:

- **🐛 Bug Reports**: Found something broken? Let us know!
- **💡 Feature Requests**: Have an idea? Share it!
- **📝 Documentation**: Help others understand DAZZLE
- **🔧 Code**: Fix bugs or implement new features
- **🎨 Examples**: Create example projects showcasing DAZZLE
- **🧪 Tests**: Improve test coverage
- **💬 Discussions**: Help answer questions and support users

## 🚀 Getting Started

### Development Setup

1. **Fork and Clone**
   ```bash
   git clone https://github.com/manwithacat/dazzle.git
   cd dazzle
   ```

2. **Set Up Python Environment**
   ```bash
   # Requires Python 3.12+ (uv provisions it automatically).
   uv sync --extra dev        # creates .venv + editable install from uv.lock
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Development Dependencies**
   `uv sync` (above) already installed them from `uv.lock`. Prefer pip instead?
   ```bash
   python3 -m venv venv && source venv/bin/activate && pip install -e ".[dev]"
   ```

4. **Install Pre-commit Hooks** (recommended)
   ```bash
   pip install pre-commit
   pre-commit install
   ```

   This will automatically run linting, formatting, and type checking before each commit.

5. **Verify Installation**
   ```bash
   dazzle --help
   pytest
   ```

### Making Your First Contribution

1. **Pick an Issue**: Browse [open issues](https://github.com/manwithacat/dazzle/issues) or create a new one
2. **Comment**: Let others know you're working on it
3. **Branch**: Create a feature branch (`git checkout -b feature/amazing-feature`)
4. **Code**: Make your changes
5. **Test**: Ensure tests pass
6. **Commit**: Write clear commit messages
7. **Push**: Push to your fork
8. **PR**: Open a pull request

## 📋 Development Workflow

### Before You Start

- **Check Existing Work**: Search issues and PRs to avoid duplicates
- **Discuss Big Changes**: For major features, open an issue first to discuss approach
- **Read the Specs**: Check [devdocs/](devdocs/) for relevant specification documents

### Code Quality

We maintain high code quality standards:

```bash
# Run all pre-commit hooks manually
pre-commit run --all-files

# Run tests
pytest

# Run tests with coverage
pytest --cov=src/dazzle --cov-report=html

# Type checking
mypy src/dazzle

# Linting
ruff check src/ tests/

# Format code
ruff format src/ tests/
```

**Note**: If you installed pre-commit hooks, these checks will run automatically on `git commit`.

### Testing

- **Write Tests**: All new features should include tests
- **Validate Examples**: Run `python tests/build_validation/validate_examples.py`
- **Manual Testing**: Test with real DSL files in `examples/`

### Commit Messages

Write clear, descriptive commit messages:

```
Add hover documentation for entity fields

- Implement rich markdown formatting for field types
- Include field modifiers and constraints in hover
- Add examples for common field patterns

Closes #123
```

### Releases & versioning

Every push to `main` gets a unique `vMAJOR.MINOR.PATCH` tag (via `/bump patch`) for
deployment traceability — but **only minor/major releases (`vX.Y.0`) are published**
to PyPI, Homebrew, and GitHub Releases. Patch tags (`vX.Y.1+`) exist for traceability
and are **not** published. To cut a published release, bump the minor: `/bump minor`.

To keep the public record tidy, on each minor release a workflow prunes patch
**tags + GitHub Releases** whose minor series has fallen outside the most recent 5
(`vX.Y.0` anchors are kept forever; the commits remain on `main`, and a tag→SHA
backup is written before deleting). See `scripts/prune_old_patch_releases.py`.

## 🎯 Contribution Ideas

Here are some areas where we'd love your help:

### 🔰 Good First Issues

Perfect for newcomers:

- **Add More Field Types**: Extend DSL with new field types (e.g., `url`, `phone`, `color`)
- **Improve Error Messages**: Make validation errors more helpful
- **Add DSL Examples**: Create example projects for common use cases
- **Documentation**: Fix typos, clarify concepts, add diagrams
- **Tests**: Increase test coverage for edge cases

### 🔌 Backend Development

Create new backends to generate different outputs:

- **Django Backend**: Generate Django models, admin, views
  - Models with proper field mappings
  - Admin configuration
  - REST API views
  - Migrations generation

- **FastAPI Backend**: Generate FastAPI endpoints
  - Pydantic models from entities
  - CRUD endpoints for each entity
  - SQLAlchemy models
  - API documentation

- **Prisma Backend**: Generate Prisma schema
  - Schema.prisma file generation
  - Relationship mappings
  - Migration support

- **GraphQL Backend**: Generate GraphQL schema
  - Type definitions
  - Resolvers
  - Mutations for CRUD operations

- **React/Next.js Frontend**: Generate UI components
  - Form components for surfaces
  - List views
  - Detail views
  - TypeScript types

### 💡 IDE Support

Expand IDE support beyond VSCode:

- **JetBrains Plugin**: PyCharm, IntelliJ IDEA support
- **Emacs Mode**: Major mode for Emacs
- **Vim Plugin**: Syntax highlighting and LSP support
- **Web IDE**: Browser-based DAZZLE editor with live preview

### 🎨 LSP Enhancements

Improve the Language Server Protocol implementation:

- **Code Actions**: Quick fixes for common errors
- **Refactoring**: Rename entities, extract modules
- **Code Lens**: Show field counts, surface usage
- **Semantic Highlighting**: Better syntax coloring
- **Snippets**: Templates for common patterns
- **Validation Rules**: Additional lint checks

### 📊 Tooling & Analysis

Build tools to help developers:

- **DSL Formatter**: Auto-format DSL files
- **Migration Tool**: Generate migrations between DSL versions
- **Visual Editor**: Drag-and-drop entity designer
- **Dependency Graph**: Visualize module relationships
- **Coverage Report**: Track which entities/surfaces are tested
- **Performance Profiler**: Identify slow validation rules

### 🌐 Integration & Services

Add support for popular services:

- **Auth Providers**: Auth0, Firebase, Supabase presets
- **Databases**: Connection presets for PostgreSQL, MySQL, MongoDB
- **Cloud Platforms**: AWS, GCP, Azure deployment configs
- **API Services**: Stripe, SendGrid, Twilio integrations
- **Monitoring**: Sentry, DataDog, New Relic instrumentation

### 🧪 Testing & Quality

Improve testing infrastructure:

- **LLM Context Testing**: Validate that LLMs can understand DAZZLE projects
- **Performance Benchmarks**: Track build times and memory usage
- **Mutation Testing**: Ensure test quality with mutation testing
- **E2E Tests**: Full workflow testing from DSL to deployment
- **Fuzzing**: Random DSL generation for robustness testing

### 📚 Documentation & Learning

Help others learn DAZZLE:

- **Video Tutorials**: Screen recordings showing DAZZLE workflows
- **Interactive Tutorial**: Step-by-step guide in the browser
- **Best Practices Guide**: Patterns and anti-patterns
- **Migration Guides**: Moving from other tools to DAZZLE
- **Case Studies**: Real-world DAZZLE applications
- **Comparison Guide**: DAZZLE vs Prisma, Terraform, etc.

### 🚀 Infrastructure & DevOps

Make deployment easier:

- **Terraform Modules**: Infrastructure as code
- **GitHub Actions**: Ready-to-use CI/CD workflows
- **Monitoring Stack**: Prometheus, Grafana dashboards

## 🏗️ Architecture Overview

Understanding DAZZLE's architecture helps you contribute effectively:

### Core Components

```
src/dazzle/
├── core/           # Core language implementation
│   ├── parser.py   # DSL parser (lark-based)
│   ├── ir.py       # Intermediate representation
│   ├── linker.py   # Module resolution and linking
│   └── lint.py     # Semantic validation
├── backends/       # Code generators
│   ├── openapi/    # OpenAPI 3.0 backend
│   └── base.py     # Backend interface
├── lsp/            # Language Server Protocol
│   └── server.py   # LSP implementation
└── cli/            # Command-line interface
    └── main.py     # CLI entry point
```

### Key Concepts

- **Parser**: Converts `.dsl` text to AST using Lark grammar
- **IR (Intermediate Representation)**: Type-safe Python models (Pydantic)
- **Linker**: Resolves cross-module references and builds AppSpec
- **Validator**: Checks semantic rules and constraints
- **Backends**: Transform IR into concrete artifacts
- **Stacks**: Coordinated multi-backend generation

See [devdocs/README.md](devdocs/README.md) for detailed documentation.

## 💬 Communication

### Getting Help

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions, ideas, show-and-tell
- **Documentation**: Check [docs/](docs/) and [devdocs/](devdocs/)

### Code Review

All contributions go through code review:

- Be patient and respectful
- Respond to feedback constructively
- Iterate based on suggestions
- Ask questions if anything is unclear

We aim to review PRs within 48 hours.

## 📜 Coding Standards

### Python Code

- **Style**: Follow PEP 8, enforced by `ruff`
- **Type Hints**: Use type annotations everywhere
- **Docstrings**: Document public APIs with Google-style docstrings
- **Imports**: Group by standard library, third-party, local
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes

### DSL Grammar

When modifying the grammar (`src/dazzle/core/grammar.lark`):

- Keep syntax minimal and consistent
- Add examples for new features
- Update documentation
- Consider LLM tokenization efficiency

### Tests

- **Unit Tests**: Test individual functions and classes
- **Integration Tests**: Test component interactions
- **E2E Tests**: Test full workflows
- **Naming**: `test_<feature>_<scenario>_<expected_result>`

### Documentation

- **User Docs** (`docs/`): For DAZZLE users
- **Dev Docs** (`devdocs/`): For contributors
- **Code Comments**: Explain why, not what
- **Examples**: Show real-world usage

## 🎉 Recognition

Contributors are recognized in:

- Release notes
- CONTRIBUTORS.md file
- Git history
- Our gratitude! 🙏

## ⚖️ License

By contributing, you agree that your contributions will be licensed under the MIT License.

## 🤝 Code of Conduct

Be kind, respectful, and professional. We're all here to learn and build something great together.

### Expected Behavior

- Welcome newcomers
- Be patient with questions
- Give constructive feedback
- Celebrate successes
- Assume good intentions

### Unacceptable Behavior

- Harassment or discrimination
- Trolling or insulting comments
- Personal attacks
- Unwelcome sexual attention
- Publishing others' private information

## 📞 Contact

- **Issues**: [GitHub Issues](https://github.com/manwithacat/dazzle/issues)
- **Discussions**: [GitHub Discussions](https://github.com/manwithacat/dazzle/discussions)
- **Security**: Report security issues privately (see SECURITY.md)

---

Thank you for contributing to DAZZLE! Every contribution, no matter how small, makes a difference. We're excited to see what you'll build! 🚀
