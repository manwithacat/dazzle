"""
Hooks for Django Micro backend.

Pre-build and post-build hooks for Django-specific tasks.
"""

from .post_build import (
    CreateSuperuserCredentialsHook,
    SetupUvEnvironmentHook,
    CreateMigrationsHook,
    RunMigrationsHook,
    CreateSuperuserHook,
    DisplayDjangoInstructionsHook,
    RunTestsHook,
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
