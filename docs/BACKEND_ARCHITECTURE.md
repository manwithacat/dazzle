# Backend Architecture - Modular Design

## Problem Statement

Current backend implementation issues:
1. **Monolithic files** - 1000+ lines in single .py files (django_micro.py, express_micro.py)
2. **Poor separation of concerns** - Models, views, templates, deployment all mixed together
3. **No extensibility** - Can't add pre/post-build hooks
4. **Hard to test** - Can't test individual components in isolation
5. **Difficult to maintain** - Hard to find and modify specific functionality
6. **No provisioning support** - Can't surface default credentials or setup instructions

## Proposed Architecture

### Directory Structure

```
backends/
├── __init__.py                      # Backend registry
├── base/
│   ├── __init__.py
│   ├── backend.py                   # Base Backend class
│   ├── hooks.py                     # Hook system
│   ├── generator.py                 # Base generator utilities
│   └── utils.py                     # Common utilities
│
├── django_micro/
│   ├── __init__.py                  # Backend registration
│   ├── backend.py                   # DjangoMicroBackend class
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── models.py               # Model generation
│   │   ├── forms.py                # Form generation
│   │   ├── views.py                # View generation
│   │   ├── urls.py                 # URL routing
│   │   ├── templates.py            # Template generation
│   │   ├── settings.py             # Django settings
│   │   ├── admin.py                # Admin configuration
│   │   └── deployment.py           # Deployment configs
│   ├── hooks/
│   │   ├── __init__.py
│   │   ├── pre_build.py            # Pre-build hooks
│   │   └── post_build.py           # Post-build hooks
│   └── utils.py                    # Django-specific utilities
│
├── express_micro/
│   ├── __init__.py
│   ├── backend.py
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── routes.py
│   │   ├── templates.py
│   │   ├── server.py
│   │   ├── admin.py
│   │   └── deployment.py
│   ├── hooks/
│   │   ├── __init__.py
│   │   ├── pre_build.py
│   │   └── post_build.py
│   └── utils.py
│
└── [other_backends]/
    └── ...
```

### Component Responsibilities

#### Base Classes

**`base/backend.py`**
```python
class Backend(ABC):
    """Base backend with hook support."""

    @abstractmethod
    def generate(self, spec: AppSpec, output_dir: Path, **options) -> None:
        """Generate artifacts from spec."""
        pass

    def run_pre_build_hooks(self, context: HookContext) -> List[HookResult]:
        """Run pre-build hooks."""
        pass

    def run_post_build_hooks(self, context: HookContext) -> List[HookResult]:
        """Run post-build hooks."""
        pass
```

**`base/hooks.py`**
```python
class Hook(ABC):
    """Base hook class."""
    name: str
    description: str

    @abstractmethod
    def execute(self, context: HookContext) -> HookResult:
        """Execute the hook."""
        pass

class HookContext:
    """Context passed to hooks."""
    spec: AppSpec
    output_dir: Path
    backend_name: str
    options: Dict[str, Any]
    artifacts: Dict[str, Any]  # Generated files, credentials, etc.

class HookResult:
    """Result from hook execution."""
    success: bool
    message: str
    artifacts: Dict[str, Any]  # New data to add to context
    display_to_user: bool = False  # Should this be shown to user?
```

#### Generator Classes

**Pattern for each generator:**
```python
class ModelsGenerator:
    """Generates Django models from entities."""

    def __init__(self, spec: AppSpec, output_dir: Path):
        self.spec = spec
        self.output_dir = output_dir

    def generate(self) -> GeneratorResult:
        """Generate models.py file."""
        code = self._build_code()
        file_path = self.output_dir / "app" / "models.py"
        file_path.write_text(code)

        return GeneratorResult(
            files_created=[file_path],
            artifacts={"model_names": [e.name for e in self.spec.entities]}
        )

    def _build_code(self) -> str:
        """Build the models.py content."""
        pass

class GeneratorResult:
    """Result from a generator."""
    files_created: List[Path]
    artifacts: Dict[str, Any]
    errors: List[str] = []
```

---

## Hook System

### Hook Types

#### 1. Pre-Build Hooks
Run before any code generation:
- Validate backend-specific requirements
- Check for required tools (Node.js, Python version)
- Create necessary directories
- Initialize git repo

#### 2. Post-Build Hooks
Run after code generation:
- Create admin superuser
- Initialize database
- Generate default credentials
- Create .env file with secrets
- Display setup instructions
- Run linters/formatters
- Generate documentation

### Hook Examples

#### Example 1: Generate Admin Credentials

**`django_micro/hooks/post_build.py`**
```python
class CreateSuperuserHook(Hook):
    """Create Django superuser with default credentials."""

    name = "create_superuser"
    description = "Create admin user for Django Admin"

    def execute(self, context: HookContext) -> HookResult:
        import secrets

        # Generate random password
        password = secrets.token_urlsafe(16)
        username = "admin"
        email = "admin@example.com"

        # Create credentials file
        creds_file = context.output_dir / ".admin_credentials"
        creds_file.write_text(f"""
Django Admin Credentials
========================
Username: {username}
Password: {password}
Email: {email}

IMPORTANT: Change these credentials in production!

To access admin:
1. python manage.py migrate
2. Visit http://localhost:8000/admin/
3. Login with credentials above
""")

        # Create management command to set this up
        self._create_init_command(context.output_dir, username, email, password)

        return HookResult(
            success=True,
            message=f"Admin credentials created in .admin_credentials",
            artifacts={
                "admin_username": username,
                "admin_password": password,
                "admin_email": email,
            },
            display_to_user=True
        )

    def _create_init_command(self, output_dir: Path, username: str,
                            email: str, password: str) -> None:
        """Create management command to initialize admin user."""
        # Generate management/commands/init_admin.py
        pass
```

#### Example 2: Environment Setup

**`express_micro/hooks/post_build.py`**
```python
class CreateEnvFileHook(Hook):
    """Create .env file with default configuration."""

    name = "create_env"
    description = "Generate .env file with configuration"

    def execute(self, context: HookContext) -> HookResult:
        import secrets

        # Generate secrets
        session_secret = secrets.token_hex(32)
        admin_secret = secrets.token_hex(32)

        env_content = f"""
# Generated by DAZZLE - {context.backend_name}
NODE_ENV=development
PORT=3000

# Session secret - change in production!
SESSION_SECRET={session_secret}

# Admin secret - change in production!
ADMIN_SECRET={admin_secret}

# Database
DATABASE_URL=sqlite:./database.sqlite
"""

        env_file = context.output_dir / context.spec.name / ".env"
        env_file.write_text(env_content)

        return HookResult(
            success=True,
            message=".env file created with development settings",
            artifacts={
                "env_file": str(env_file),
                "session_secret": session_secret,
            },
            display_to_user=True
        )
```

#### Example 3: Display Setup Instructions

**`base/hooks.py`** (common hook)
```python
class DisplaySetupInstructionsHook(Hook):
    """Show user how to run their generated application."""

    name = "display_instructions"
    description = "Display setup instructions"

    def execute(self, context: HookContext) -> HookResult:
        instructions = self._build_instructions(context)

        # Print to console with nice formatting
        print("\n" + "="*60)
        print("🎉 Build Complete!")
        print("="*60)
        print(instructions)
        print("="*60 + "\n")

        return HookResult(
            success=True,
            message="Instructions displayed",
            display_to_user=False  # Already printed
        )

    def _build_instructions(self, context: HookContext) -> str:
        """Build backend-specific instructions."""
        # Check context.backend_name and generate appropriate instructions
        pass
```

---

## Migration Path

### Phase 1: Create Base Infrastructure
1. Create `base/` module with hook system
2. Update `Backend` base class to support hooks
3. Create example hooks
4. Update backend registry for modular backends

### Phase 2: Refactor Django Micro
1. Create `django_micro/` directory structure
2. Split monolithic file into generators
3. Move to modular structure
4. Add pre/post-build hooks
5. Test thoroughly

### Phase 3: Refactor Express Micro
1. Same process as Django Micro
2. Reuse patterns from Django refactor

### Phase 4: Update Other Backends
1. Django API
2. OpenAPI
3. Infrastructure backends

### Phase 5: Documentation & Testing
1. Update backend development guide
2. Add hook development guide
3. Add unit tests for each component
4. Add integration tests

---

## Benefits

### For Maintainers
- **Easier to navigate** - Find specific functionality quickly
- **Easier to test** - Test components in isolation
- **Easier to modify** - Change one aspect without affecting others
- **Easier to review** - Smaller, focused files in PRs

### For Contributors
- **Lower barrier to entry** - Understand one component at a time
- **Clear structure** - Know where to add new features
- **Reusable patterns** - Follow established generator patterns

### For Users
- **Better error messages** - Know which component failed
- **Provisioning support** - Get default credentials automatically
- **Setup guidance** - Post-build hooks show next steps
- **Customization** - Override specific generators

### For Backend Developers
- **Hook extensibility** - Add custom pre/post-build logic
- **Generator reuse** - Share generators across backends
- **Clear contracts** - Well-defined interfaces between components

---

## Hook Use Cases

### Pre-Build Hooks
1. **Validate dependencies** - Check Node.js/Python version
2. **Validate spec** - Backend-specific validation
3. **Check file permissions** - Ensure output dir is writable
4. **Initialize directories** - Create required folders
5. **Backup existing** - Save previous build before overwrite

### Post-Build Hooks
1. **Generate credentials** - Admin passwords, API keys
2. **Initialize database** - Run migrations, create schema
3. **Install dependencies** - Run npm install, pip install
4. **Format code** - Run prettier, black
5. **Generate docs** - Create README, API docs
6. **Display instructions** - Show setup steps
7. **Create .gitignore** - Based on backend type
8. **Set file permissions** - Make scripts executable
9. **Run tests** - Validate generated code works
10. **Deploy** - Push to hosting platform (optional)

---

## Configuration

### Backend-level Configuration

**`django_micro/__init__.py`**
```python
from .backend import DjangoMicroBackend
from .hooks.post_build import CreateSuperuserHook, CreateEnvFileHook

# Register backend with hooks
backend = DjangoMicroBackend()
backend.register_post_build_hook(CreateSuperuserHook())
backend.register_post_build_hook(CreateEnvFileHook())

__all__ = ['DjangoMicroBackend']
```

### User-level Configuration (Future)

**`dazzle.toml`**
```toml
[stack]
name = "micro"

[hooks]
# Enable/disable hooks
pre_build = ["validate_dependencies"]
post_build = ["create_superuser", "display_instructions"]

# Skip specific hooks
skip = ["install_dependencies"]

[hooks.create_superuser]
username = "custom_admin"
email = "admin@myapp.com"
# password = auto-generated if not specified
```

---

## Example: Refactored Backend Structure

### Before (Monolithic)

**`backends/django_micro.py`** - 1200 lines
```python
class DjangoMicroBackend(Backend):
    def generate(self, spec, output_dir, **options):
        # 1200 lines of mixed concerns
        self._generate_models()
        self._generate_forms()
        self._generate_views()
        self._generate_templates()
        self._generate_urls()
        self._generate_settings()
        self._generate_deployment()
```

### After (Modular)

**`backends/django_micro/backend.py`** - 100 lines
```python
from .generators import (
    ModelsGenerator, FormsGenerator, ViewsGenerator,
    TemplatesGenerator, UrlsGenerator, SettingsGenerator,
    DeploymentGenerator
)

class DjangoMicroBackend(Backend):
    def generate(self, spec, output_dir, **options):
        # Run pre-build hooks
        self.run_pre_build_hooks(context)

        # Run generators
        generators = [
            ModelsGenerator(spec, output_dir),
            FormsGenerator(spec, output_dir),
            ViewsGenerator(spec, output_dir),
            TemplatesGenerator(spec, output_dir),
            UrlsGenerator(spec, output_dir),
            SettingsGenerator(spec, output_dir),
            DeploymentGenerator(spec, output_dir),
        ]

        for generator in generators:
            result = generator.generate()
            self.collect_artifacts(result)

        # Run post-build hooks
        self.run_post_build_hooks(context)
```

**`backends/django_micro/generators/models.py`** - 200 lines
```python
class ModelsGenerator:
    """Focused on just model generation."""

    def generate(self) -> GeneratorResult:
        code = self._build_models_code()
        file_path = self.output_dir / "app" / "models.py"
        file_path.write_text(code)
        return GeneratorResult(files_created=[file_path])

    def _build_models_code(self) -> str:
        # Model generation logic
        pass
```

---

## Testing Strategy

### Unit Tests
```python
def test_models_generator():
    """Test model generation in isolation."""
    spec = create_test_spec()
    output_dir = tmp_path()

    generator = ModelsGenerator(spec, output_dir)
    result = generator.generate()

    assert len(result.files_created) == 1
    assert (output_dir / "app" / "models.py").exists()

    code = (output_dir / "app" / "models.py").read_text()
    assert "class Task(models.Model)" in code
```

### Integration Tests
```python
def test_django_micro_backend():
    """Test full backend generation."""
    spec = create_test_spec()
    output_dir = tmp_path()

    backend = DjangoMicroBackend()
    backend.generate(spec, output_dir)

    # Verify all files created
    assert (output_dir / "manage.py").exists()
    assert (output_dir / "app" / "models.py").exists()

    # Verify hooks ran
    assert (output_dir / ".admin_credentials").exists()
```

### Hook Tests
```python
def test_create_superuser_hook():
    """Test superuser creation hook."""
    context = create_test_context()
    hook = CreateSuperuserHook()

    result = hook.execute(context)

    assert result.success
    assert "admin_username" in result.artifacts
    assert result.display_to_user == True
```

---

## Next Steps

1. **Review & Approve Architecture** - Team review
2. **Create Base Infrastructure** - Hook system, base classes
3. **Refactor One Backend** - Start with django_micro
4. **Test Thoroughly** - Ensure no regression
5. **Document Patterns** - Guide for other backends
6. **Roll Out to Other Backends** - Systematic refactoring

---

## Open Questions

1. **Async hooks?** - Should hooks support async execution?
2. **Hook dependencies?** - Can hooks depend on other hooks?
3. **Hook errors?** - How to handle hook failures (fail build vs. warn)?
4. **Generator ordering?** - Fixed order or dependency-based?
5. **Backward compatibility?** - Support old monolithic backends during migration?

---

## Success Metrics

- **Lines per file** < 300 (down from 1200+)
- **Components testable** in isolation
- **Hook coverage** - All backends have provisioning hooks
- **Development time** - Faster to add new features
- **Contributor onboarding** - Easier to understand codebase
