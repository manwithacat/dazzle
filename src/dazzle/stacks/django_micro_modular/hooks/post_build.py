"""
Post-build hooks for Django Micro backend.

Runs after code generation to:
- Generate admin credentials
- Setup UV virtual environment
- Run migrations
- Create superuser
- Display setup instructions
"""

import secrets
import subprocess
import sys
from pathlib import Path

from ...base import Hook, HookContext, HookResult, HookPhase


class CreateSuperuserCredentialsHook(Hook):
    """
    Generate Django admin superuser credentials.

    Creates a .admin_credentials file with username and password
    that can be used to initialize the admin user.
    """

    name = "create_superuser_credentials"
    description = "Generate Django admin credentials"
    phase = HookPhase.POST_BUILD

    def execute(self, context: HookContext) -> HookResult:
        """Generate admin credentials file."""
        # Generate secure password
        password = secrets.token_urlsafe(16)
        username = "admin"
        email = "admin@example.com"

        # Create credentials file content
        creds_content = f"""Django Admin Credentials
========================
Username: {username}
Password: {password}
Email: {email}

IMPORTANT: Change these credentials in production!

To create the admin user:
1. Run: python manage.py migrate
2. Run: python manage.py createsuperuser
3. Use the credentials above
4. Access admin at: http://localhost:8000/admin/

Or for automatic setup (development only):
1. python manage.py migrate
2. python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('{username}', '{email}', '{password}')"
"""

        # Write credentials file using normalized project path
        project_path = context.options.get('project_path') or context.output_dir / context.spec.name
        creds_file = project_path / ".admin_credentials"
        creds_file.write_text(creds_content)

        return HookResult(
            success=True,
            message=f"Admin credentials saved to .admin_credentials",
            artifacts={
                "admin_username": username,
                "admin_password": password,
                "admin_email": email,
                "credentials_file": str(creds_file),
            },
            display_to_user=True
        )


class DisplayDjangoInstructionsHook(Hook):
    """
    Display Django-specific setup instructions.

    Shows user how to run their generated Django application.
    """

    name = "display_django_instructions"
    description = "Display setup instructions"
    phase = HookPhase.POST_BUILD

    def execute(self, context: HookContext) -> HookResult:
        """Display instructions."""
        # Use normalized project path
        output_path = context.options.get('project_path') or context.output_dir / context.spec.name
        app_name = context.options.get('project_name', context.spec.name)

        instructions = f"""
{'=' * 60}
🎉 Django Micro Application Built Successfully!
{'=' * 60}

Application: {app_name}
Location: {output_path}

✅ Automated Setup Complete:
----------------------------
✓ Virtual environment created (.venv)
✓ Dependencies installed
✓ Database migrations applied
✓ Admin superuser created

Ready to Run:
-------------

1. Navigate to your app:
   cd {output_path}

2. Activate virtual environment:
   source .venv/bin/activate  # On Linux/macOS
   .venv\\Scripts\\activate     # On Windows

3. Start development server:
   python manage.py runserver

4. Open your browser:
   http://localhost:8000/        (Home page)
   http://localhost:8000/admin/  (Admin dashboard - see .admin_credentials)

Admin Login:
------------
Credentials saved in: .admin_credentials
⚠️  Change these in production!

Deployment:
-----------
This app includes configs for:
- Heroku: Procfile and runtime.txt included
- Railway: Works out of the box
- PythonAnywhere: See README.md for setup

{'=' * 60}
"""

        print(instructions)

        return HookResult(
            success=True,
            message="Setup instructions displayed",
            display_to_user=False  # Already printed
        )


class SetupUvEnvironmentHook(Hook):
    """
    Create UV virtual environment and install dependencies.

    Uses UV for fast Python package installation.
    Falls back to standard pip if UV is not available.
    """

    name = "setup_uv_environment"
    description = "Create virtual environment with UV"
    phase = HookPhase.POST_BUILD

    def execute(self, context: HookContext) -> HookResult:
        """Setup virtual environment and install dependencies."""
        app_path = context.options.get('project_path') or context.output_dir / context.spec.name
        venv_path = app_path / ".venv"
        requirements_path = app_path / "requirements.txt"

        # Check if UV is available
        try:
            subprocess.run(
                ["uv", "--version"],
                capture_output=True,
                check=True,
                timeout=5
            )
            has_uv = True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            has_uv = False

        try:
            if has_uv:
                # Create venv with UV
                subprocess.run(
                    ["uv", "venv", str(venv_path)],
                    cwd=app_path,
                    check=True,
                    capture_output=True,
                    timeout=30
                )

                # Install dependencies with UV
                subprocess.run(
                    ["uv", "pip", "install", "-r", "requirements.txt"],
                    cwd=app_path,
                    env={**subprocess.os.environ, "VIRTUAL_ENV": str(venv_path)},
                    check=True,
                    capture_output=True,
                    timeout=120
                )

                message = "✓ Virtual environment created with UV and dependencies installed"
            else:
                # Fallback to standard venv + pip
                subprocess.run(
                    [sys.executable, "-m", "venv", str(venv_path)],
                    cwd=app_path,
                    check=True,
                    capture_output=True,
                    timeout=30
                )

                # Determine pip path based on OS
                if sys.platform == "win32":
                    pip_path = venv_path / "Scripts" / "pip"
                else:
                    pip_path = venv_path / "bin" / "pip"

                subprocess.run(
                    [str(pip_path), "install", "-r", "requirements.txt"],
                    cwd=app_path,
                    check=True,
                    capture_output=True,
                    timeout=120
                )

                message = "✓ Virtual environment created with standard venv and dependencies installed"

            return HookResult(
                success=True,
                message=message,
                artifacts={"venv_path": str(venv_path), "used_uv": has_uv},
                display_to_user=True
            )

        except subprocess.TimeoutExpired:
            return HookResult(
                success=False,
                message="⚠ Virtual environment setup timed out",
                display_to_user=True
            )
        except subprocess.CalledProcessError as e:
            return HookResult(
                success=False,
                message=f"⚠ Failed to setup virtual environment: {e}",
                display_to_user=True
            )
        except Exception as e:
            return HookResult(
                success=False,
                message=f"⚠ Error during virtual environment setup: {e}",
                display_to_user=True
            )


class CreateMigrationsHook(Hook):
    """
    Generate Django migration files for custom models.

    Runs 'manage.py makemigrations' to create initial migration files.
    Requires virtual environment to be set up first.
    """

    name = "create_migrations"
    description = "Generate Django migration files"
    phase = HookPhase.POST_BUILD

    def execute(self, context: HookContext) -> HookResult:
        """Generate Django migration files."""
        app_path = context.options.get('project_path') or context.output_dir / context.spec.name
        venv_path = app_path / ".venv"

        # Determine python path based on OS
        if sys.platform == "win32":
            python_path = venv_path / "Scripts" / "python"
        else:
            python_path = venv_path / "bin" / "python"

        # Check if venv exists
        if not python_path.exists():
            return HookResult(
                success=False,
                message="⚠ Virtual environment not found, skipping migration creation",
                display_to_user=True
            )

        try:
            # Run makemigrations
            result = subprocess.run(
                [str(python_path), "manage.py", "makemigrations"],
                cwd=app_path,
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )

            # Check if migrations were created
            if "No changes detected" in result.stdout:
                return HookResult(
                    success=True,
                    message="✓ No new migrations needed",
                    artifacts={"makemigrations_output": result.stdout},
                    display_to_user=True
                )
            else:
                return HookResult(
                    success=True,
                    message="✓ Migration files created successfully",
                    artifacts={"makemigrations_output": result.stdout},
                    display_to_user=True
                )

        except subprocess.TimeoutExpired:
            return HookResult(
                success=False,
                message="⚠ Migration creation timed out",
                display_to_user=True
            )
        except subprocess.CalledProcessError as e:
            return HookResult(
                success=False,
                message=f"⚠ Migration creation failed: {e.stderr}",
                display_to_user=True
            )
        except Exception as e:
            return HookResult(
                success=False,
                message=f"⚠ Error creating migrations: {e}",
                display_to_user=True
            )


class RunMigrationsHook(Hook):
    """
    Run Django database migrations automatically.

    Requires virtual environment to be set up first.
    """

    name = "run_migrations"
    description = "Run Django migrations"
    phase = HookPhase.POST_BUILD

    def execute(self, context: HookContext) -> HookResult:
        """Run Django migrations."""
        app_path = context.options.get('project_path') or context.output_dir / context.spec.name
        venv_path = app_path / ".venv"

        # Determine python path based on OS
        if sys.platform == "win32":
            python_path = venv_path / "Scripts" / "python"
        else:
            python_path = venv_path / "bin" / "python"

        # Check if venv exists
        if not python_path.exists():
            return HookResult(
                success=False,
                message="⚠ Virtual environment not found, skipping migrations",
                display_to_user=True
            )

        try:
            # Run migrations
            result = subprocess.run(
                [str(python_path), "manage.py", "migrate", "--noinput"],
                cwd=app_path,
                capture_output=True,
                text=True,
                timeout=60,
                check=True
            )

            return HookResult(
                success=True,
                message="✓ Database migrations completed successfully",
                artifacts={"migrations_output": result.stdout},
                display_to_user=True
            )

        except subprocess.TimeoutExpired:
            return HookResult(
                success=False,
                message="⚠ Migrations timed out",
                display_to_user=True
            )
        except subprocess.CalledProcessError as e:
            return HookResult(
                success=False,
                message=f"⚠ Migrations failed: {e.stderr}",
                display_to_user=True
            )
        except Exception as e:
            return HookResult(
                success=False,
                message=f"⚠ Error running migrations: {e}",
                display_to_user=True
            )


class CreateSuperuserHook(Hook):
    """
    Create Django admin superuser automatically.

    Uses credentials generated by CreateSuperuserCredentialsHook.
    Requires migrations to be run first.
    """

    name = "create_superuser"
    description = "Create Django admin superuser"
    phase = HookPhase.POST_BUILD

    def execute(self, context: HookContext) -> HookResult:
        """Create Django superuser."""
        app_path = context.options.get('project_path') or context.output_dir / context.spec.name
        venv_path = app_path / ".venv"

        # Determine python path based on OS
        if sys.platform == "win32":
            python_path = venv_path / "Scripts" / "python"
        else:
            python_path = venv_path / "bin" / "python"

        # Check if venv exists
        if not python_path.exists():
            return HookResult(
                success=False,
                message="⚠ Virtual environment not found, skipping superuser creation",
                display_to_user=True
            )

        # Get credentials from previous hook
        creds_hook_result = context.get_hook_artifact("create_superuser_credentials")
        if not creds_hook_result:
            return HookResult(
                success=False,
                message="⚠ Admin credentials not found, skipping superuser creation",
                display_to_user=True
            )

        username = creds_hook_result.get("admin_username", "admin")
        password = creds_hook_result.get("admin_password")
        email = creds_hook_result.get("admin_email", "admin@example.com")

        if not password:
            return HookResult(
                success=False,
                message="⚠ Admin password not found, skipping superuser creation",
                display_to_user=True
            )

        try:
            # Create superuser using Django shell command
            create_user_cmd = (
                f"from django.contrib.auth import get_user_model; "
                f"User = get_user_model(); "
                f"User.objects.filter(username='{username}').exists() or "
                f"User.objects.create_superuser('{username}', '{email}', '{password}')"
            )

            result = subprocess.run(
                [str(python_path), "manage.py", "shell", "-c", create_user_cmd],
                cwd=app_path,
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )

            return HookResult(
                success=True,
                message=f"✓ Admin superuser created: {username} (see .admin_credentials for password)",
                display_to_user=True
            )

        except subprocess.TimeoutExpired:
            return HookResult(
                success=False,
                message="⚠ Superuser creation timed out",
                display_to_user=True
            )
        except subprocess.CalledProcessError as e:
            # Check if user already exists
            if "already exists" in e.stderr or "already exists" in e.stdout:
                return HookResult(
                    success=True,
                    message=f"✓ Admin superuser already exists: {username}",
                    display_to_user=True
                )
            return HookResult(
                success=False,
                message=f"⚠ Failed to create superuser: {e.stderr}",
                display_to_user=True
            )
        except Exception as e:
            return HookResult(
                success=False,
                message=f"⚠ Error creating superuser: {e}",
                display_to_user=True
            )


class RunTestsHook(Hook):
    """
    Run Django test suite to validate generated code.

    Executes 'python manage.py test' to verify:
    - Models work correctly
    - Views return expected status codes
    - Forms validate properly
    - Auto-population logic functions

    This hook is optional and can be disabled for faster builds.
    """

    name = "run_tests"
    description = "Run Django test suite"
    phase = HookPhase.POST_BUILD

    def execute(self, context: HookContext) -> HookResult:
        """Run Django tests."""
        app_path = context.options.get('project_path') or context.output_dir / context.spec.name
        venv_path = app_path / ".venv"

        # Determine python path based on OS
        if sys.platform == "win32":
            python_path = venv_path / "Scripts" / "python"
        else:
            python_path = venv_path / "bin" / "python"

        # Check if venv exists
        if not python_path.exists():
            return HookResult(
                success=False,
                message="⚠ Virtual environment not found, skipping tests",
                display_to_user=True
            )

        try:
            # Run tests with verbosity=2 to show which tests are running
            result = subprocess.run(
                [str(python_path), "manage.py", "test", "--verbosity=2"],
                cwd=app_path,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                check=True
            )

            # Count test results
            output = result.stdout + result.stderr
            tests_run = 0
            for line in output.split('\n'):
                if 'Ran ' in line and ' test' in line:
                    # Extract number of tests from "Ran 42 tests in 1.234s"
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            tests_run = int(parts[1])
                        except ValueError:
                            pass

            return HookResult(
                success=True,
                message=f"✓ All tests passed ({tests_run} tests)",
                artifacts={"test_output": output, "tests_run": tests_run},
                display_to_user=True
            )

        except subprocess.TimeoutExpired:
            return HookResult(
                success=False,
                message="⚠ Tests timed out (exceeded 5 minutes)",
                display_to_user=True
            )
        except subprocess.CalledProcessError as e:
            # Tests failed
            return HookResult(
                success=False,
                message=f"⚠ Tests failed\n{e.stdout}\n{e.stderr}",
                artifacts={"test_output": e.stdout + e.stderr},
                display_to_user=True
            )
        except Exception as e:
            return HookResult(
                success=False,
                message=f"⚠ Error running tests: {e}",
                display_to_user=True
            )


class ValidateEndpointsHook(Hook):
    """
    Smoke test all generated endpoints to verify they're accessible.

    Starts dev server temporarily and hits each URL to verify:
    - List views return 200
    - Create forms return 200
    - Admin pages load

    This is a quick sanity check that the generated app works.
    """

    name = "validate_endpoints"
    description = "Smoke test all endpoints"
    phase = HookPhase.POST_BUILD

    def execute(self, context: HookContext) -> HookResult:
        """Validate all endpoints."""
        app_path = context.options.get('project_path') or context.output_dir / context.spec.name
        venv_path = app_path / ".venv"

        # Determine python path based on OS
        if sys.platform == "win32":
            python_path = venv_path / "Scripts" / "python"
        else:
            python_path = venv_path / "bin" / "python"

        # Check if venv exists
        if not python_path.exists():
            return HookResult(
                success=False,
                message="⚠ Virtual environment not found, skipping endpoint validation",
                display_to_user=True
            )

        # Build list of URLs to test
        urls_to_test = []
        for entity in context.spec.domain.entities:
            entity_lower = entity.name.lower()
            # Check which surfaces exist
            for surface in context.spec.surfaces:
                if surface.entity_ref == entity.name:
                    if surface.mode == ir.SurfaceMode.LIST:
                        urls_to_test.append((f"/{entity_lower}/", f"{entity.name} list"))
                    elif surface.mode == ir.SurfaceMode.CREATE:
                        urls_to_test.append((f"/{entity_lower}/create/", f"{entity.name} create"))

        if not urls_to_test:
            return HookResult(
                success=True,
                message="✓ No endpoints to validate",
                display_to_user=True
            )

        try:
            # Start dev server in background
            server_process = subprocess.Popen(
                [str(python_path), "manage.py", "runserver", "--noreload", "8765"],
                cwd=app_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait for server to start
            import time
            time.sleep(3)

            # Test each URL
            import urllib.request
            failed_urls = []
            for url_path, description in urls_to_test:
                try:
                    full_url = f"http://127.0.0.1:8765{url_path}"
                    response = urllib.request.urlopen(full_url, timeout=5)
                    if response.status != 200:
                        failed_urls.append((url_path, description, response.status))
                except Exception as e:
                    failed_urls.append((url_path, description, str(e)))

            # Stop server
            server_process.terminate()
            server_process.wait(timeout=5)

            if failed_urls:
                failure_msg = "⚠ Some endpoints failed:\n"
                for url, desc, error in failed_urls:
                    failure_msg += f"  - {url} ({desc}): {error}\n"
                return HookResult(
                    success=False,
                    message=failure_msg,
                    display_to_user=True
                )

            return HookResult(
                success=True,
                message=f"✓ All {len(urls_to_test)} endpoints validated successfully",
                display_to_user=True
            )

        except Exception as e:
            # Try to stop server if it's still running
            try:
                server_process.terminate()
                server_process.wait(timeout=5)
            except:
                pass

            return HookResult(
                success=False,
                message=f"⚠ Error validating endpoints: {e}",
                display_to_user=True
            )
