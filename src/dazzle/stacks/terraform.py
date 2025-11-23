"""
Terraform infrastructure backend for DAZZLE.

Generates cloud-ready infrastructure using Terraform.
Supports AWS initially, with extensibility for GCP and Azure.
"""

from pathlib import Path
from typing import Any

from ..core import ir
from ..core.errors import BackendError
from ..core.infra_analyzer import InfraRequirements, analyze_infra_requirements
from ..core.manifest import TerraformConfig
from . import Backend, BackendCapabilities


class TerraformStack(Backend):
    """
    Terraform stack for cloud infrastructure deployment.

    Creates modular Terraform configuration with:
    - Compute resources (ECS, Cloud Run)
    - Managed database (RDS, Cloud SQL)
    - Managed cache (ElastiCache, MemoryStore)
    - Managed queue (SQS, Pub/Sub)
    - Networking (VPC, subnets, security groups)
    - Per-environment wrappers (dev, staging, prod)
    """

    def generate(
        self,
        appspec: ir.AppSpec,
        output_dir: Path,
        terraform_config: TerraformConfig | None = None,
        **options: Any,
    ) -> None:
        """
        Generate Terraform infrastructure.

        Args:
            appspec: Application specification from IR
            output_dir: Output directory (typically infra/terraform/)
            terraform_config: Terraform configuration from manifest
            **options: Additional options

        Raises:
            BackendError: If generation fails
        """
        try:
            # Ensure output directory exists
            output_dir.mkdir(parents=True, exist_ok=True)

            # Use default config if not provided
            if terraform_config is None:
                terraform_config = TerraformConfig()

            # Analyze infrastructure requirements
            requirements = analyze_infra_requirements(appspec)

            # Validate cloud provider
            if terraform_config.cloud_provider not in ["aws", "gcp", "azure"]:
                raise BackendError(
                    f"Unsupported cloud provider: {terraform_config.cloud_provider}. "
                    f"Supported: aws, gcp, azure"
                )

            # Generate modules
            modules_dir = output_dir / "modules"
            self._generate_modules(modules_dir, appspec, terraform_config, requirements)

            # Generate environment wrappers
            envs_dir = output_dir / "envs"
            self._generate_environments(envs_dir, appspec, terraform_config, requirements)

            # Generate root README
            self._generate_readme(output_dir, appspec, terraform_config, requirements)

        except Exception as e:
            if isinstance(e, BackendError):
                raise
            raise BackendError(f"Failed to generate Terraform infrastructure: {e}") from e

    def get_capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            name="terraform",
            description="Generate Terraform configuration for cloud deployment",
            output_formats=["tf"],
            supports_incremental=False,
            requires_config=True,
        )

    def _generate_modules(
        self,
        modules_dir: Path,
        appspec: ir.AppSpec,
        config: TerraformConfig,
        requirements: InfraRequirements,
    ) -> None:
        """Generate Terraform modules."""
        modules_dir.mkdir(parents=True, exist_ok=True)

        # Always generate network module
        self._generate_network_module(modules_dir, config)

        # Generate app module
        self._generate_app_module(modules_dir, appspec, config, requirements)

        # Generate database module if needed
        if requirements.needs_database:
            self._generate_db_module(modules_dir, config)

        # Generate cache module if needed
        if requirements.needs_cache or requirements.needs_queue:
            self._generate_cache_module(modules_dir, config)

    def _generate_network_module(self, modules_dir: Path, config: TerraformConfig) -> None:
        """Generate network module (VPC, subnets, security groups)."""
        network_dir = modules_dir / "network"
        network_dir.mkdir(parents=True, exist_ok=True)

        if config.cloud_provider == "aws":
            main_tf = """# Network module - VPC and subnets

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "${var.environment}-vpc"
    Environment = var.environment
  }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name        = "${var.environment}-public-${count.index + 1}"
    Environment = var.environment
  }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name        = "${var.environment}-private-${count.index + 1}"
    Environment = var.environment
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name        = "${var.environment}-igw"
    Environment = var.environment
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name        = "${var.environment}-public-rt"
    Environment = var.environment
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

data "aws_availability_zones" "available" {
  state = "available"
}

output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}
"""
            (network_dir / "main.tf").write_text(main_tf)

    def _generate_app_module(
        self,
        modules_dir: Path,
        appspec: ir.AppSpec,
        config: TerraformConfig,
        requirements: InfraRequirements,
    ) -> None:
        """Generate app module (ECS, Cloud Run, etc.)."""
        app_dir = modules_dir / "app"
        app_dir.mkdir(parents=True, exist_ok=True)

        if config.cloud_provider == "aws":
            main_tf = f'''# App module - ECS Fargate service

variable "environment" {{
  description = "Environment name"
  type        = string
}}

variable "vpc_id" {{
  description = "VPC ID"
  type        = string
}}

variable "subnet_ids" {{
  description = "Subnet IDs for ECS tasks"
  type        = list(string)
}}

variable "container_image" {{
  description = "Docker image for the application"
  type        = string
}}

variable "container_port" {{
  description = "Container port"
  type        = number
  default     = 8000
}}

variable "environment_variables" {{
  description = "Environment variables for the container"
  type        = map(string)
  default     = {{}}
}}

# ECS Cluster
resource "aws_ecs_cluster" "main" {{
  name = "${{var.environment}}-{appspec.name}-cluster"

  tags = {{
    Environment = var.environment
  }}
}}

# Security group for ECS tasks
resource "aws_security_group" "ecs_tasks" {{
  name        = "${{var.environment}}-ecs-tasks-sg"
  description = "Security group for ECS tasks"
  vpc_id      = var.vpc_id

  ingress {{
    from_port   = var.container_port
    to_port     = var.container_port
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  tags = {{
    Environment = var.environment
  }}
}}

# IAM role for ECS task execution
resource "aws_iam_role" "ecs_execution_role" {{
  name = "${{var.environment}}-ecs-execution-role"

  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [
      {{
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {{
          Service = "ecs-tasks.amazonaws.com"
        }}
      }}
    ]
  }})
}}

resource "aws_iam_role_policy_attachment" "ecs_execution_role_policy" {{
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}}

# ECS Task Definition
resource "aws_ecs_task_definition" "app" {{
  family                   = "${{var.environment}}-{appspec.name}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn

  container_definitions = jsonencode([
    {{
      name      = "{appspec.name}"
      image     = var.container_image
      essential = true

      portMappings = [
        {{
          containerPort = var.container_port
          protocol      = "tcp"
        }}
      ]

      environment = [
        for key, value in var.environment_variables : {{
          name  = key
          value = value
        }}
      ]

      logConfiguration = {{
        logDriver = "awslogs"
        options = {{
          "awslogs-group"         = "/ecs/${{var.environment}}-{appspec.name}"
          "awslogs-region"        = "us-east-1"
          "awslogs-stream-prefix" = "ecs"
        }}
      }}
    }}
  ])
}}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "app" {{
  name              = "/ecs/${{var.environment}}-{appspec.name}"
  retention_in_days = 7
}}

# ECS Service
resource "aws_ecs_service" "app" {{
  name            = "${{var.environment}}-{appspec.name}-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {{
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }}
}}

output "cluster_name" {{
  value = aws_ecs_cluster.main.name
}}

output "service_name" {{
  value = aws_ecs_service.app.name
}}
'''
            (app_dir / "main.tf").write_text(main_tf)

    def _generate_db_module(self, modules_dir: Path, config: TerraformConfig) -> None:
        """Generate database module (RDS, Cloud SQL)."""
        db_dir = modules_dir / "db"
        db_dir.mkdir(parents=True, exist_ok=True)

        if config.cloud_provider == "aws":
            main_tf = """# Database module - RDS PostgreSQL

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for DB"
  type        = list(string)
}

variable "db_name" {
  description = "Database name"
  type        = string
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "dazzle_admin"
}

variable "db_password" {
  description = "Database master password"
  type        = string
  sensitive   = true
}

# Security group for RDS
resource "aws_security_group" "rds" {
  name        = "${var.environment}-rds-sg"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Environment = var.environment
  }
}

# DB Subnet Group
resource "aws_db_subnet_group" "main" {
  name       = "${var.environment}-db-subnet-group"
  subnet_ids = var.subnet_ids

  tags = {
    Environment = var.environment
  }
}

# RDS Instance
resource "aws_db_instance" "main" {
  identifier             = "${var.environment}-db"
  engine                 = "postgres"
  engine_version         = "15.3"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  storage_type           = "gp2"
  db_name                = var.db_name
  username               = var.db_username
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  skip_final_snapshot    = true
  publicly_accessible    = false

  tags = {
    Environment = var.environment
  }
}

output "endpoint" {
  value = aws_db_instance.main.endpoint
}

output "database_name" {
  value = aws_db_instance.main.db_name
}
"""
            (db_dir / "main.tf").write_text(main_tf)

    def _generate_cache_module(self, modules_dir: Path, config: TerraformConfig) -> None:
        """Generate cache module (ElastiCache, MemoryStore)."""
        cache_dir = modules_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        if config.cloud_provider == "aws":
            main_tf = """# Cache module - ElastiCache Redis

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for cache"
  type        = list(string)
}

# Security group for ElastiCache
resource "aws_security_group" "redis" {
  name        = "${var.environment}-redis-sg"
  description = "Security group for ElastiCache Redis"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Environment = var.environment
  }
}

# Cache Subnet Group
resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.environment}-cache-subnet-group"
  subnet_ids = var.subnet_ids
}

# ElastiCache Redis
resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "${var.environment}-redis"
  engine               = "redis"
  node_type            = "cache.t3.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.redis.id]

  tags = {
    Environment = var.environment
  }
}

output "endpoint" {
  value = aws_elasticache_cluster.redis.cache_nodes[0].address
}

output "port" {
  value = aws_elasticache_cluster.redis.port
}
"""
            (cache_dir / "main.tf").write_text(main_tf)

    def _generate_environments(
        self,
        envs_dir: Path,
        appspec: ir.AppSpec,
        config: TerraformConfig,
        requirements: InfraRequirements,
    ) -> None:
        """Generate per-environment wrappers."""
        for env in config.environments:
            self._generate_environment(envs_dir, env, appspec, config, requirements)

    def _generate_environment(
        self,
        envs_dir: Path,
        env_name: str,
        appspec: ir.AppSpec,
        config: TerraformConfig,
        requirements: InfraRequirements,
    ) -> None:
        """Generate single environment wrapper."""
        env_dir = envs_dir / env_name
        env_dir.mkdir(parents=True, exist_ok=True)

        # main.tf
        main_tf = f'''# {env_name.capitalize()} environment for {appspec.name}

terraform {{
  required_version = ">= 1.0"
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = var.aws_region
}}

# Network
module "network" {{
  source      = "../../modules/network"
  environment = "{env_name}"
}}

# App
module "app" {{
  source          = "../../modules/app"
  environment     = "{env_name}"
  vpc_id          = module.network.vpc_id
  subnet_ids      = module.network.public_subnet_ids
  container_image = var.container_image

  environment_variables = {{'''

        if requirements.needs_database:
            main_tf += """
    DATABASE_HOST = module.db.endpoint
    DATABASE_NAME = module.db.database_name"""

        if requirements.needs_cache or requirements.needs_queue:
            main_tf += """
    REDIS_HOST = module.cache.endpoint
    REDIS_PORT = tostring(module.cache.port)"""

        main_tf += """
  }
}
"""

        if requirements.needs_database:
            main_tf += (
                '''
# Database
module "db" {
  source      = "../../modules/db"
  environment = "'''
                + env_name
                + """"
  vpc_id      = module.network.vpc_id
  subnet_ids  = module.network.private_subnet_ids
  db_name     = var.db_name
  db_username = var.db_username
  db_password = var.db_password
}
"""
            )

        if requirements.needs_cache or requirements.needs_queue:
            main_tf += (
                '''
# Cache
module "cache" {
  source      = "../../modules/cache"
  environment = "'''
                + env_name
                + """"
  vpc_id      = module.network.vpc_id
  subnet_ids  = module.network.private_subnet_ids
}
"""
            )

        (env_dir / "main.tf").write_text(main_tf)

        # variables.tf
        variables_tf = """variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "container_image" {
  description = "Docker image for application"
  type        = string
}
"""

        if requirements.needs_database:
            variables_tf += """
variable "db_name" {
  description = "Database name"
  type        = string
}

variable "db_username" {
  description = "Database username"
  type        = string
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}
"""

        (env_dir / "variables.tf").write_text(variables_tf)

        # terraform.tfvars (example)
        tfvars = f"""# Example terraform.tfvars for {env_name}
aws_region      = "us-east-1"
container_image = "your-registry/{appspec.name}:latest"
"""

        if requirements.needs_database:
            tfvars += f'''db_name     = "{appspec.name}_{env_name}"
db_username = "dazzle_admin"
# db_password should be set via environment variable or secrets manager
'''

        (env_dir / "terraform.tfvars.example").write_text(tfvars)

        # backend.tf
        backend_tf = f'''# Remote state configuration for {env_name}
terraform {{
  backend "s3" {{
    bucket = "your-terraform-state-bucket"
    key    = "{appspec.name}/{env_name}/terraform.tfstate"
    region = "us-east-1"
    # dynamodb_table = "terraform-locks"
    # encrypt        = true
  }}
}}
'''

        (env_dir / "backend.tf.example").write_text(backend_tf)

    def _generate_readme(
        self,
        output_dir: Path,
        appspec: ir.AppSpec,
        config: TerraformConfig,
        requirements: InfraRequirements,
    ) -> None:
        """Generate README with Terraform usage instructions."""
        readme_content = f"""# Terraform Infrastructure for {appspec.title or appspec.name}

Generated by DAZZLE infrastructure backend for {config.cloud_provider.upper()}.

## Structure

```
terraform/
├── modules/          # Reusable Terraform modules
│   ├── network/      # VPC, subnets, security groups
│   ├── app/          # ECS/compute resources
"""

        if requirements.needs_database:
            readme_content += """│   ├── db/           # RDS PostgreSQL
"""

        if requirements.needs_cache or requirements.needs_queue:
            readme_content += """│   ├── cache/        # ElastiCache Redis
"""

        readme_content += """└── envs/            # Per-environment configurations
"""

        for env in config.environments:
            readme_content += f"""    ├── {env}/
"""

        readme_content += """
## Prerequisites

1. Terraform >= 1.0
2. AWS CLI configured with credentials
3. Docker image pushed to container registry

## Quick Start

### 1. Configure Backend

Copy the example backend configuration:

```bash
cd envs/dev
cp backend.tf.example backend.tf
# Edit backend.tf with your S3 bucket details
```

### 2. Set Variables

Copy and edit tfvars:

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
```

### 3. Initialize Terraform

```bash
terraform init
```

### 4. Plan Changes

```bash
terraform plan
```

### 5. Apply

```bash
terraform apply
```

## Environment Management

### Development
```bash
cd envs/dev
terraform apply
```

### Staging
```bash
cd envs/staging
terraform apply
```

### Production
```bash
cd envs/prod
terraform apply
```

## Sensitive Variables

Database passwords and secrets should be provided via:

1. **Environment variables:**
   ```bash
   export TF_VAR_db_password="your-password"
   ```

2. **Terraform Cloud/Enterprise:**
   Configure in workspace variables

3. **AWS Secrets Manager:**
   Reference in Terraform configuration

## Outputs

After applying, get connection details:

```bash
terraform output
```

## Cleanup

To destroy infrastructure:

```bash
terraform destroy
```

**Warning:** This will delete all resources including databases.

---

Generated by DAZZLE Terraform backend
"""

        (output_dir / "README.md").write_text(readme_content)


__all__ = ["TerraformStack"]
