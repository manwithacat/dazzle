"""
Hooks for Django Micro backend.

Pre-build and post-build hooks for Django-specific tasks.
"""

from .post_build import (
    CreateMigrationsHook,
    CreateSuperuserCredentialsHook,
    CreateSuperuserHook,
    DisplayDjangoInstructionsHook,
    RunMigrationsHook,
    RunTestsHook,
    SetupUvEnvironmentHook,
    ValidateEndpointsHook,
)

__all__ = [
    "CreateSuperuserCredentialsHook",
    "SetupUvEnvironmentHook",
    "CreateMigrationsHook",
    "RunMigrationsHook",
    "CreateSuperuserHook",
    "DisplayDjangoInstructionsHook",
    "RunTestsHook",
    "ValidateEndpointsHook",
]
