"""
Modular backend base class with hook support.

Extends the base Backend class to add:
- Hook system for pre/post-build extensibility
- Generator orchestration
- Artifact collection
- Progress reporting
"""

from pathlib import Path
from typing import List, Optional

from .. import Backend
from ...core import ir
from ...core.errors import BackendError

from .hooks import Hook, HookContext, HookManager, HookPhase, HookResult
from .generator import Generator, GeneratorResult


class ModularBackend(Backend):
    """
    Base class for modular backends with hook support.

    Provides infrastructure for:
    - Running pre/post-build hooks
    - Orchestrating multiple generators
    - Collecting artifacts
    - Reporting progress

    Usage:
        class DjangoMicroBackend(ModularBackend):
            def __init__(self):
                super().__init__()
                self.register_hooks()

            def register_hooks(self):
                self.add_pre_build_hook(ValidateDependenciesHook())
                self.add_post_build_hook(CreateSuperuserHook())

            def get_generators(self, spec, output_dir, **options):
                return [
                    ModelsGenerator(spec, output_dir),
                    ViewsGenerator(spec, output_dir),
                    # ... more generators
                ]
    """

    def __init__(self):
        """Initialize modular backend with hook manager."""
        self.hook_manager = HookManager()
        self.artifacts = {}

    def add_hook(self, hook: Hook) -> None:
        """Register a hook."""
        self.hook_manager.register(hook)

    def add_pre_build_hook(self, hook: Hook) -> None:
        """Register a pre-build hook."""
        hook.phase = HookPhase.PRE_BUILD
        self.hook_manager.register(hook)

    def add_post_build_hook(self, hook: Hook) -> None:
        """Register a post-build hook."""
        hook.phase = HookPhase.POST_BUILD
        self.hook_manager.register(hook)

    def get_generators(self, spec: ir.AppSpec, output_dir: Path, **options) -> List[Generator]:
        """
        Get the list of generators to run.

        Override this to provide backend-specific generators.

        Args:
            spec: Application specification
            output_dir: Output directory
            **options: Backend options

        Returns:
            List of Generator instances
        """
        return []

    def generate(self, appspec: ir.AppSpec, output_dir: Path, **options) -> None:
        """
        Generate artifacts with hook support.

        Execution flow:
        1. Run pre-build hooks
        2. Run generators
        3. Collect artifacts
        4. Run post-build hooks
        5. Display results

        Args:
            appspec: Application specification
            output_dir: Output directory
            **options: Backend options
        """
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create hook context
        context = HookContext(
            spec=appspec,
            output_dir=output_dir,
            backend_name=self.__class__.__name__,
            options=options,
            artifacts={}
        )

        # Phase 1: Pre-build hooks
        pre_results = self._run_pre_build_hooks(context)
        self._display_hook_results("Pre-build", pre_results)

        # Check if any pre-build hook failed critically
        if any(not r.success and r.stop_on_failure for r in pre_results):
            raise BackendError("Pre-build hook failed, aborting generation")

        # Phase 2: Run generators
        gen_results = self._run_generators(appspec, output_dir, context, **options)
        self._collect_generator_artifacts(gen_results, context)

        # Check if any generator failed
        if any(not r.success for r in gen_results):
            errors = []
            for r in gen_results:
                errors.extend(r.errors)
            raise BackendError(f"Generation failed: {'; '.join(errors)}")

        # Phase 3: Post-build hooks
        post_results = self._run_post_build_hooks(context)
        self._display_hook_results("Post-build", post_results)

        # Store artifacts for inspection
        self.artifacts = context.artifacts

    def _run_pre_build_hooks(self, context: HookContext) -> List[HookResult]:
        """Run pre-build hooks."""
        return self.hook_manager.run_phase(HookPhase.PRE_BUILD, context)

    def _run_post_build_hooks(self, context: HookContext) -> List[HookResult]:
        """Run post-build hooks."""
        return self.hook_manager.run_phase(HookPhase.POST_BUILD, context)

    def _run_generators(
        self,
        spec: ir.AppSpec,
        output_dir: Path,
        context: HookContext,
        **options
    ) -> List[GeneratorResult]:
        """Run all generators."""
        results = []
        generators = self.get_generators(spec, output_dir, **options)

        for generator in generators:
            result = generator.generate()
            results.append(result)

            # Stop if generator failed
            if not result.success:
                break

        return results

    def _collect_generator_artifacts(
        self,
        results: List[GeneratorResult],
        context: HookContext
    ) -> None:
        """Collect artifacts from generators into context."""
        for result in results:
            for key, value in result.artifacts.items():
                context.add_artifact(key, value)

    def _display_hook_results(self, phase: str, results: List[HookResult]) -> None:
        """Display hook results to user."""
        if not results:
            return

        # Find results that should be displayed
        display_results = [r for r in results if r.display_to_user]

        if not display_results:
            return

        print(f"\n{phase} Hooks:")
        for result in display_results:
            print(f"  {result}")

    def get_artifacts(self, output_dir: Path = None) -> dict:
        """
        Get artifacts from last generation.

        Args:
            output_dir: Optional output directory (for compatibility with CLI)

        Returns:
            Dictionary of artifacts from generators and hooks
        """
        return self.artifacts
