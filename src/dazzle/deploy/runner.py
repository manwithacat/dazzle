"""
Deployment runner for orchestrating CDK code generation.

The DeploymentRunner analyzes the AppSpec, determines AWS requirements,
and runs stack generators to produce CDK Python code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .analyzer import AWSRequirements, analyze_aws_requirements
from .config import DeploymentConfig, load_deployment_config
from .generator import CDKGeneratorResult, StackGenerator
from .stacks import (
    ComputeStackGenerator,
    DataStackGenerator,
    MessagingStackGenerator,
    NetworkStackGenerator,
    ObservabilityStackGenerator,
)

if TYPE_CHECKING:
    from dazzle.core import ir
    from dazzle.core.infra_analyzer import InfraRequirements


DEPLOY_VERSION = "0.1.0"


# =============================================================================
# Deployment Result
# =============================================================================


@dataclass
class DeploymentResult:
    """Result from a deployment generation run."""

    files_created: list[Path] = field(default_factory=list)
    stacks_generated: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    verified: bool = False

    @property
    def success(self) -> bool:
        """Check if generation was successful."""
        return len(self.errors) == 0

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)

    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)

    def merge_generator_result(self, result: CDKGeneratorResult, prefix: str = "") -> None:
        """Merge a generator result into this deployment result."""
        self.files_created.extend(result.files_created)
        self.stacks_generated.extend(result.stack_names)
        self.errors.extend(result.errors)
        self.warnings.extend(result.warnings)

        if prefix:
            for key, value in result.artifacts.items():
                self.artifacts[f"{prefix}.{key}"] = value
        else:
            self.artifacts.update(result.artifacts)

    def summary(self) -> dict[str, Any]:
        """Get a summary of the deployment result."""
        return {
            "success": self.success,
            "files_created": len(self.files_created),
            "stacks_generated": self.stacks_generated,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# =============================================================================
# Deployment Runner
# =============================================================================


class DeploymentRunner:
    """
    Orchestrates AWS CDK code generation from AppSpec.

    Usage:
        runner = DeploymentRunner(spec, project_root)
        result = runner.run()
    """

    def __init__(
        self,
        spec: ir.AppSpec,
        project_root: Path,
        config: DeploymentConfig | None = None,
    ):
        self.spec = spec
        self.project_root = project_root

        # Load config
        if config is None:
            toml_path = project_root / "dazzle.toml"
            config = load_deployment_config(toml_path)

        self.config = config
        self.output_dir = config.output.get_output_path(project_root)

        # Analyze infrastructure requirements
        from dazzle.core.infra_analyzer import analyze_infra_requirements

        self.infra_reqs: InfraRequirements = analyze_infra_requirements(spec)
        self.aws_reqs: AWSRequirements = analyze_aws_requirements(spec, self.infra_reqs, config)

    def run(self, dry_run: bool = False) -> DeploymentResult:
        """
        Run the deployment code generation.

        Args:
            dry_run: If True, only preview what would be generated

        Returns:
            DeploymentResult with generated files and status
        """
        result = DeploymentResult()

        if dry_run:
            return self._dry_run(result)

        # Ensure output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "stacks").mkdir(exist_ok=True)

        # Generate stacks in dependency order
        generators = self._get_generators()

        for generator in generators:
            gen_result = generator.generate()
            result.merge_generator_result(gen_result)

            if not gen_result.success:
                return result  # Stop on first error

        # Generate CDK app entry point
        app_result = self._generate_cdk_app(result.stacks_generated)
        result.merge_generator_result(app_result, "app")

        # Generate supporting files
        support_result = self._generate_supporting_files()
        result.merge_generator_result(support_result, "support")

        # Verify generated code
        result.verified = self._verify_output()

        return result

    def _dry_run(self, result: DeploymentResult) -> DeploymentResult:
        """Preview what would be generated without writing files."""
        result.warnings.append("DRY RUN - No files will be written")

        # List stacks that would be generated
        generators = self._get_generators()
        for generator in generators:
            if generator.should_generate():
                result.stacks_generated.append(generator.stack_name)

        # Add estimated files
        result.artifacts["estimated_files"] = [
            str(self.output_dir / "app.py"),
            str(self.output_dir / "cdk.json"),
            str(self.output_dir / "requirements.txt"),
            str(self.output_dir / "README.md"),
        ]

        for stack_name in result.stacks_generated:
            result.artifacts["estimated_files"].append(
                str(self.output_dir / "stacks" / f"{stack_name.lower()}_stack.py")
            )

        return result

    def _get_generators(self) -> list[StackGenerator]:
        """Get stack generators in dependency order."""
        generators: list[StackGenerator] = []

        # Network (always needed)
        generators.append(
            NetworkStackGenerator(self.spec, self.aws_reqs, self.config, self.output_dir)
        )

        # Data (RDS, S3)
        generators.append(
            DataStackGenerator(self.spec, self.aws_reqs, self.config, self.output_dir)
        )

        # Messaging (SQS, EventBridge)
        generators.append(
            MessagingStackGenerator(self.spec, self.aws_reqs, self.config, self.output_dir)
        )

        # Compute (ECS, ALB) - depends on Network, Data, Messaging
        generators.append(
            ComputeStackGenerator(self.spec, self.aws_reqs, self.config, self.output_dir)
        )

        # Observability (CloudWatch) - depends on Compute
        generators.append(
            ObservabilityStackGenerator(self.spec, self.aws_reqs, self.config, self.output_dir)
        )

        return generators

    def _generate_cdk_app(self, stack_names: list[str]) -> CDKGeneratorResult:
        """Generate the CDK app entry point (app.py)."""
        result = CDKGeneratorResult()

        app_name = self._get_app_name()
        env = self.config.environment
        region = self.config.region.value

        # Build imports
        stack_imports = []
        for name in stack_names:
            class_name = f"{name}Stack"
            file_name = f"{name.lower()}_stack"
            stack_imports.append(f"from stacks.{file_name} import {class_name}")

        imports_code = "\n".join(stack_imports)

        # Build stack instantiations
        stack_inits = []

        # Network stack
        if "Network" in stack_names:
            stack_inits.append(f'''
network_stack = NetworkStack(
    app,
    "{app_name}-{env}-network",
    env=env,
)
''')

        # Data stack
        if "Data" in stack_names:
            stack_inits.append(f'''
data_stack = DataStack(
    app,
    "{app_name}-{env}-data",
    network_stack=network_stack,
    env=env,
)
''')

        # Messaging stack
        if "Messaging" in stack_names:
            stack_inits.append(f'''
messaging_stack = MessagingStack(
    app,
    "{app_name}-{env}-messaging",
    env=env,
)
''')

        # Compute stack
        if "Compute" in stack_names:
            data_arg = "data_stack=data_stack," if "Data" in stack_names else "data_stack=None,"
            messaging_arg = (
                "messaging_stack=messaging_stack,"
                if "Messaging" in stack_names
                else "messaging_stack=None,"
            )
            stack_inits.append(f'''
compute_stack = ComputeStack(
    app,
    "{app_name}-{env}-compute",
    network_stack=network_stack,
    {data_arg}
    {messaging_arg}
    env=env,
)
''')

        # Observability stack
        if "Observability" in stack_names:
            data_arg = "data_stack=data_stack," if "Data" in stack_names else "data_stack=None,"
            messaging_arg = (
                "messaging_stack=messaging_stack,"
                if "Messaging" in stack_names
                else "messaging_stack=None,"
            )
            stack_inits.append(f'''
observability_stack = ObservabilityStack(
    app,
    "{app_name}-{env}-observability",
    compute_stack=compute_stack,
    {data_arg}
    {messaging_arg}
    env=env,
)
''')

        inits_code = "\n".join(stack_inits)

        code = f'''#!/usr/bin/env python3
"""
CDK application for {self.spec.name}.

Generated by: dazzle deploy generate v{DEPLOY_VERSION}
Environment: {env}
Region: {region}

Deployment:
    pip install -r requirements.txt
    cdk bootstrap         # One-time setup per account/region
    cdk deploy --all      # Deploy all stacks
    cdk destroy --all     # Tear down all stacks
"""

import aws_cdk as cdk

{imports_code}


app = cdk.App()

# Environment configuration
env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region="{region}",
)
{inits_code}

app.synth()
'''

        app_path = self.output_dir / "app.py"
        app_path.write_text(code)
        result.add_file(app_path)

        return result

    def _generate_supporting_files(self) -> CDKGeneratorResult:
        """Generate requirements.txt, cdk.json, README.md."""
        result = CDKGeneratorResult()

        app_name = self._get_app_name()
        env = self.config.environment

        # requirements.txt
        requirements = """aws-cdk-lib>=2.100.0
constructs>=10.0.0
"""
        req_path = self.output_dir / "requirements.txt"
        req_path.write_text(requirements)
        result.add_file(req_path)

        # cdk.json
        cdk_json = """{
  "app": "python3 app.py",
  "watch": {
    "include": ["**"],
    "exclude": [
      "README.md",
      "cdk*.json",
      "requirements*.txt",
      "**/*.pyc",
      "**/__pycache__",
      ".git",
      ".venv"
    ]
  },
  "context": {
    "@aws-cdk/aws-apigateway:usagePlanKeyOrderInsensitiveId": true,
    "@aws-cdk/core:stackRelativeExports": true,
    "@aws-cdk/aws-rds:lowercaseDbIdentifier": true,
    "@aws-cdk/aws-lambda:recognizeVersionProps": true,
    "@aws-cdk/aws-ecs:arnFormatIncludesClusterName": true
  }
}
"""
        cdk_path = self.output_dir / "cdk.json"
        cdk_path.write_text(cdk_json)
        result.add_file(cdk_path)

        # stacks/__init__.py
        stacks_init = '''"""CDK stacks for the application."""
'''
        stacks_init_path = self.output_dir / "stacks" / "__init__.py"
        stacks_init_path.write_text(stacks_init)
        result.add_file(stacks_init_path)

        # README.md
        readme = f"""# {self.spec.name} Infrastructure

Generated by `dazzle deploy generate` v{DEPLOY_VERSION}

## Prerequisites

- Python 3.11+
- AWS CLI configured with credentials
- AWS CDK CLI: `npm install -g aws-cdk`

## Setup

```bash
cd {self.output_dir.name}
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

## Deploy

```bash
# Bootstrap CDK (first time only, per account/region)
cdk bootstrap

# Deploy all stacks
cdk deploy --all

# Or deploy specific stacks
cdk deploy {app_name}-{env}-network
cdk deploy {app_name}-{env}-data
cdk deploy {app_name}-{env}-compute
```

## Push Docker Image

After deployment, push your application image:

```bash
# Get ECR login
aws ecr get-login-password --region {self.config.region.value} | docker login --username AWS --password-stdin <account>.dkr.ecr.{self.config.region.value}.amazonaws.com

# Build and push
docker build -t {app_name}:latest .
docker tag {app_name}:latest <account>.dkr.ecr.{self.config.region.value}.amazonaws.com/{app_name}:latest
docker push <account>.dkr.ecr.{self.config.region.value}.amazonaws.com/{app_name}:latest

# Force new deployment
aws ecs update-service --cluster {app_name}-{env} --service {app_name}-{env} --force-new-deployment
```

## Destroy

```bash
cdk destroy --all
```

## Stacks

| Stack | Resources |
|-------|-----------|
| Network | VPC, Subnets, Security Groups |
| Data | RDS (PostgreSQL), S3 |
| Messaging | SQS, EventBridge |
| Compute | ECS Fargate, ALB, ECR |
| Observability | CloudWatch Dashboard, Alarms |
"""
        readme_path = self.output_dir / "README.md"
        readme_path.write_text(readme)
        result.add_file(readme_path)

        return result

    def _verify_output(self) -> bool:
        """Verify the generated CDK code has no Dazzle dependencies."""
        forbidden_patterns = [
            "from dazzle",
            "import dazzle",
        ]

        for py_file in self.output_dir.rglob("*.py"):
            content = py_file.read_text()
            for pattern in forbidden_patterns:
                if pattern in content:
                    return False

        return True

    def _get_app_name(self) -> str:
        """Get sanitized application name."""
        name = self.spec.name.lower()
        name = "".join(c if c.isalnum() else "-" for c in name)
        while "--" in name:
            name = name.replace("--", "-")
        return name.strip("-")

    def plan(self) -> dict[str, Any]:
        """
        Get a plan of what would be deployed without generating code.

        Returns:
            Dictionary with infrastructure plan
        """
        return {
            "app_name": self._get_app_name(),
            "environment": self.config.environment,
            "region": self.config.region.value,
            "requirements": self.aws_reqs.summary(),
            "stacks": [g.stack_name for g in self._get_generators() if g.should_generate()],
            "config": {
                "compute": {
                    "size": self.config.compute.size.value,
                    "cpu": self.config.compute.cpu,
                    "memory": self.config.compute.memory,
                    "min_capacity": self.config.compute.min_capacity,
                    "max_capacity": self.config.compute.max_capacity,
                    "use_spot": self.config.compute.use_spot,
                },
                "database": {
                    "size": self.config.database.size.value,
                    "multi_az": self.config.database.multi_az,
                },
                "network": {
                    "availability_zones": self.config.network.availability_zones,
                    "nat_gateways": self.config.network.nat_gateways,
                },
            },
        }


__all__ = [
    "DeploymentResult",
    "DeploymentRunner",
    "DEPLOY_VERSION",
]
