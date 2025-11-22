from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import tomllib


@dataclass
class DockerConfig:
    """Docker infrastructure configuration."""
    variant: str = "compose"  # "compose" or "dockerfile"
    image_name: Optional[str] = None
    base_image: str = "python:3.11-slim"
    port: int = 8000


@dataclass
class TerraformConfig:
    """Terraform infrastructure configuration."""
    root_module: str = "./infra/terraform"
    cloud_provider: str = "aws"  # "aws", "gcp", "azure"
    environments: List[str] = field(default_factory=lambda: ["dev", "staging", "prod"])
    region: Optional[str] = None


@dataclass
class InfraConfig:
    """Infrastructure configuration from manifest."""
    backends: List[str] = field(default_factory=list)
    docker: DockerConfig = field(default_factory=DockerConfig)
    terraform: TerraformConfig = field(default_factory=TerraformConfig)


@dataclass
class StackConfig:
    """Stack configuration - preset combination of backends."""
    name: str
    backends: List[str] = field(default_factory=list)
    description: Optional[str] = None


@dataclass
class ProjectManifest:
    name: str
    version: str
    project_root: str
    module_paths: List[str]
    infra: Optional[InfraConfig] = None
    stack: Optional[StackConfig] = None


def load_manifest(path: Path) -> ProjectManifest:
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    project = data.get("project", {})
    modules = data.get("modules", {})
    infra_data = data.get("infra", {})
    stack_data = data.get("stack", {})

    # Parse infra config if present
    infra_config = None
    if infra_data:
        docker_data = infra_data.get("docker", {})
        terraform_data = infra_data.get("terraform", {})

        docker_config = DockerConfig(
            variant=docker_data.get("variant", "compose"),
            image_name=docker_data.get("image_name"),
            base_image=docker_data.get("base_image", "python:3.11-slim"),
            port=docker_data.get("port", 8000),
        )

        terraform_config = TerraformConfig(
            root_module=terraform_data.get("root_module", "./infra/terraform"),
            cloud_provider=terraform_data.get("cloud_provider", "aws"),
            environments=terraform_data.get("environments", ["dev", "staging", "prod"]),
            region=terraform_data.get("region"),
        )

        infra_config = InfraConfig(
            backends=infra_data.get("backends", []),
            docker=docker_config,
            terraform=terraform_config,
        )

    # Parse stack config if present
    stack_config = None
    if stack_data:
        stack_config = StackConfig(
            name=stack_data.get("name", ""),
            backends=stack_data.get("backends", []),
            description=stack_data.get("description"),
        )

    return ProjectManifest(
        name=project.get("name", "unnamed"),
        version=project.get("version", "0.0.0"),
        project_root=project.get("root", ""),
        module_paths=modules.get("paths", ["./dsl"]),
        infra=infra_config,
        stack=stack_config,
    )