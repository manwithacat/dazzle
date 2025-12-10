"""
Ejection configuration models.

Parses the [ejection] section from dazzle.toml and provides
typed configuration for all ejection adapters.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found]


class BackendFramework(str, Enum):
    """Supported backend frameworks."""

    FASTAPI = "fastapi"
    DJANGO = "django"
    FLASK = "flask"


class BackendModels(str, Enum):
    """Supported model libraries."""

    PYDANTIC_V2 = "pydantic-v2"
    SQLALCHEMY = "sqlalchemy"
    DJANGO_ORM = "django-orm"


class BackendRouting(str, Enum):
    """Backend routing styles."""

    ROUTER_MODULES = "router-modules"
    FLAT = "flat"


class FrontendFramework(str, Enum):
    """Supported frontend frameworks."""

    REACT = "react"
    VUE = "vue"
    NEXTJS = "nextjs"


class FrontendAPIClient(str, Enum):
    """Supported API client generators."""

    ZOD_FETCH = "zod-fetch"
    OPENAPI_TS = "openapi-ts"
    AXIOS = "axios"


class FrontendState(str, Enum):
    """Supported state management libraries."""

    TANSTACK_QUERY = "tanstack-query"
    SWR = "swr"
    NONE = "none"


class TestingContract(str, Enum):
    """Supported contract testing tools."""

    SCHEMATHESIS = "schemathesis"
    NONE = "none"


class TestingUnit(str, Enum):
    """Supported unit testing frameworks."""

    PYTEST = "pytest"
    UNITTEST = "unittest"
    NONE = "none"


class TestingE2E(str, Enum):
    """Supported E2E testing frameworks."""

    PLAYWRIGHT = "playwright"
    NONE = "none"


class CITemplate(str, Enum):
    """Supported CI templates."""

    GITHUB_ACTIONS = "github-actions"
    GITLAB_CI = "gitlab-ci"
    NONE = "none"


class EjectionBackendConfig(BaseModel):
    """Backend ejection configuration."""

    model_config = ConfigDict(populate_by_name=True)

    framework: BackendFramework = BackendFramework.FASTAPI
    models: BackendModels = BackendModels.PYDANTIC_V2
    async_handlers: bool = Field(default=True, alias="async")
    routing: BackendRouting = BackendRouting.ROUTER_MODULES


class EjectionFrontendConfig(BaseModel):
    """Frontend ejection configuration."""

    framework: FrontendFramework = FrontendFramework.REACT
    api_client: FrontendAPIClient = FrontendAPIClient.ZOD_FETCH
    state: FrontendState = FrontendState.TANSTACK_QUERY


class EjectionTestingConfig(BaseModel):
    """Testing ejection configuration."""

    contract: TestingContract = TestingContract.SCHEMATHESIS
    unit: TestingUnit = TestingUnit.PYTEST
    e2e: TestingE2E = TestingE2E.NONE


class EjectionCIConfig(BaseModel):
    """CI ejection configuration."""

    template: CITemplate = CITemplate.GITHUB_ACTIONS


class EjectionOutputConfig(BaseModel):
    """Output configuration."""

    directory: str = "generated/"
    clean: bool = True


class EjectionConfig(BaseModel):
    """Complete ejection configuration."""

    enabled: bool = False
    reuse_dnr: bool = False
    backend: EjectionBackendConfig = Field(default_factory=EjectionBackendConfig)
    frontend: EjectionFrontendConfig = Field(default_factory=EjectionFrontendConfig)
    testing: EjectionTestingConfig = Field(default_factory=EjectionTestingConfig)
    ci: EjectionCIConfig = Field(default_factory=EjectionCIConfig)
    output: EjectionOutputConfig = Field(default_factory=EjectionOutputConfig)

    def get_output_path(self, project_root: Path) -> Path:
        """Get absolute output directory path."""
        output_dir = Path(self.output.directory)
        if output_dir.is_absolute():
            return output_dir
        return project_root / output_dir


def load_ejection_config(toml_path: Path) -> EjectionConfig:
    """
    Load ejection configuration from dazzle.toml.

    Args:
        toml_path: Path to dazzle.toml file

    Returns:
        EjectionConfig with parsed values or defaults
    """
    if not toml_path.exists():
        return EjectionConfig()

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    ejection_data = data.get("ejection", {})

    if not ejection_data:
        return EjectionConfig()

    # Parse nested sections
    config_dict: dict[str, Any] = {
        "enabled": ejection_data.get("enabled", False),
        "reuse_dnr": ejection_data.get("reuse_dnr", False),
    }

    # Backend config
    if "backend" in ejection_data:
        backend_data = ejection_data["backend"]
        config_dict["backend"] = EjectionBackendConfig(
            framework=backend_data.get("framework", "fastapi"),
            models=backend_data.get("models", "pydantic-v2"),
            async_handlers=backend_data.get("async", True),
            routing=backend_data.get("routing", "router-modules"),
        )

    # Frontend config
    if "frontend" in ejection_data:
        frontend_data = ejection_data["frontend"]
        config_dict["frontend"] = EjectionFrontendConfig(
            framework=frontend_data.get("framework", "react"),
            api_client=frontend_data.get("api_client", "zod-fetch"),
            state=frontend_data.get("state", "tanstack-query"),
        )

    # Testing config
    if "testing" in ejection_data:
        testing_data = ejection_data["testing"]
        config_dict["testing"] = EjectionTestingConfig(
            contract=testing_data.get("contract", "schemathesis"),
            unit=testing_data.get("unit", "pytest"),
            e2e=testing_data.get("e2e", "none"),
        )

    # CI config
    if "ci" in ejection_data:
        ci_data = ejection_data["ci"]
        config_dict["ci"] = EjectionCIConfig(
            template=ci_data.get("template", "github-actions"),
        )

    # Output config
    if "output" in ejection_data:
        output_data = ejection_data["output"]
        config_dict["output"] = EjectionOutputConfig(
            directory=output_data.get("directory", "generated/"),
            clean=output_data.get("clean", True),
        )

    return EjectionConfig(**config_dict)


def get_project_config(project_root: Path) -> dict[str, Any]:
    """
    Load full project configuration from dazzle.toml.

    Args:
        project_root: Project root directory

    Returns:
        Full parsed TOML data
    """
    toml_path = project_root / "dazzle.toml"

    if not toml_path.exists():
        return {}

    with open(toml_path, "rb") as f:
        return tomllib.load(f)
