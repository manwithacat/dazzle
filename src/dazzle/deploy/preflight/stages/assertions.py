"""
Stage 2: Template Assertions.

Validates CloudFormation templates against security and best practice rules.
"""

from __future__ import annotations

from typing import Any

from ..models import (
    STAGE_ASSERTIONS,
    Finding,
    FindingSeverity,
)
from .base import PreflightStage


class AssertionsStage(PreflightStage):
    """
    Template assertions stage.

    Validates CloudFormation templates against a set of security
    and best practice rules without requiring AWS credentials.
    """

    @property
    def name(self) -> str:
        return STAGE_ASSERTIONS

    def should_skip(self) -> tuple[bool, str | None]:
        """Check if assertions should be skipped."""
        skip, reason = super().should_skip()
        if skip:
            return skip, reason

        # Skip if no templates loaded
        if not self.context.templates:
            return True, "No templates available (synth stage may have failed)"

        return False, None

    def _execute(self) -> None:
        """Execute template assertions."""
        for stack_name, template in self.context.templates.items():
            self._check_template(stack_name, template)

    def _check_template(self, stack_name: str, template: dict[str, Any]) -> None:
        """Run all checks on a single template."""
        resources = template.get("Resources", {})

        for logical_id, resource in resources.items():
            resource_type = resource.get("Type", "")
            properties = resource.get("Properties", {})

            # Run type-specific checks
            if resource_type == "AWS::RDS::DBInstance":
                self._check_rds_instance(stack_name, logical_id, properties)
            elif resource_type == "AWS::RDS::DBCluster":
                self._check_rds_cluster(stack_name, logical_id, properties)
            elif resource_type == "AWS::S3::Bucket":
                self._check_s3_bucket(stack_name, logical_id, properties)
            elif resource_type == "AWS::EC2::SecurityGroup":
                self._check_security_group(stack_name, logical_id, properties)
            elif resource_type == "AWS::ECS::TaskDefinition":
                self._check_ecs_task(stack_name, logical_id, properties)
            elif resource_type == "AWS::IAM::Role":
                self._check_iam_role(stack_name, logical_id, properties)
            elif resource_type == "AWS::IAM::Policy":
                self._check_iam_policy(stack_name, logical_id, properties)
            elif resource_type == "AWS::Lambda::Function":
                self._check_lambda_function(stack_name, logical_id, properties)
            elif resource_type == "AWS::SQS::Queue":
                self._check_sqs_queue(stack_name, logical_id, properties)

    # --- RDS Checks ---

    def _check_rds_instance(
        self, stack_name: str, logical_id: str, properties: dict[str, Any]
    ) -> None:
        """Check RDS instance configuration."""
        resource_id = f"{stack_name}/{logical_id}"

        # Check for public accessibility
        if properties.get("PubliclyAccessible", False):
            self.add_finding(
                Finding(
                    severity=FindingSeverity.CRITICAL,
                    code="RDS_PUBLIC_ACCESS",
                    message="RDS instance is publicly accessible",
                    resource=resource_id,
                    remediation="Set PubliclyAccessible to false",
                )
            )

        # Check for encryption
        if not properties.get("StorageEncrypted", False):
            self.add_finding(
                Finding(
                    severity=FindingSeverity.HIGH,
                    code="RDS_NOT_ENCRYPTED",
                    message="RDS instance storage is not encrypted",
                    resource=resource_id,
                    remediation="Set StorageEncrypted to true",
                )
            )

        # Check for deletion protection (production)
        if not properties.get("DeletionProtection", False):
            self.add_finding(
                Finding(
                    severity=FindingSeverity.INFO,
                    code="RDS_NO_DELETION_PROTECTION",
                    message="RDS instance has no deletion protection",
                    resource=resource_id,
                    remediation="Consider enabling DeletionProtection for production",
                )
            )

        # Check for backup retention
        backup_retention = properties.get("BackupRetentionPeriod", 0)
        if backup_retention == 0:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.HIGH,
                    code="RDS_NO_BACKUPS",
                    message="RDS instance has no automated backups",
                    resource=resource_id,
                    remediation="Set BackupRetentionPeriod to at least 7 days",
                )
            )

    def _check_rds_cluster(
        self, stack_name: str, logical_id: str, properties: dict[str, Any]
    ) -> None:
        """Check RDS cluster (Aurora) configuration."""
        resource_id = f"{stack_name}/{logical_id}"

        # Check for encryption
        if not properties.get("StorageEncrypted", False):
            self.add_finding(
                Finding(
                    severity=FindingSeverity.HIGH,
                    code="RDS_CLUSTER_NOT_ENCRYPTED",
                    message="RDS cluster storage is not encrypted",
                    resource=resource_id,
                    remediation="Set StorageEncrypted to true",
                )
            )

        # Check for deletion protection
        if not properties.get("DeletionProtection", False):
            self.add_finding(
                Finding(
                    severity=FindingSeverity.INFO,
                    code="RDS_CLUSTER_NO_DELETION_PROTECTION",
                    message="RDS cluster has no deletion protection",
                    resource=resource_id,
                )
            )

    # --- S3 Checks ---

    def _check_s3_bucket(
        self, stack_name: str, logical_id: str, properties: dict[str, Any]
    ) -> None:
        """Check S3 bucket configuration."""
        resource_id = f"{stack_name}/{logical_id}"

        # Check for public access block
        public_config = properties.get("PublicAccessBlockConfiguration", {})
        if not public_config:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.HIGH,
                    code="S3_NO_PUBLIC_ACCESS_BLOCK",
                    message="S3 bucket has no public access block configuration",
                    resource=resource_id,
                    remediation="Add PublicAccessBlockConfiguration with all blocks enabled",
                )
            )
        else:
            # Check individual settings
            if not public_config.get("BlockPublicAcls", False):
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.WARN,
                        code="S3_ALLOWS_PUBLIC_ACLS",
                        message="S3 bucket allows public ACLs",
                        resource=resource_id,
                        remediation="Set BlockPublicAcls to true",
                    )
                )
            if not public_config.get("BlockPublicPolicy", False):
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.WARN,
                        code="S3_ALLOWS_PUBLIC_POLICY",
                        message="S3 bucket allows public policies",
                        resource=resource_id,
                        remediation="Set BlockPublicPolicy to true",
                    )
                )

        # Check for encryption
        encryption = properties.get("BucketEncryption")
        if not encryption:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.WARN,
                    code="S3_NOT_ENCRYPTED",
                    message="S3 bucket has no encryption configuration",
                    resource=resource_id,
                    remediation="Add BucketEncryption with SSE-S3 or SSE-KMS",
                )
            )

        # Check for versioning
        versioning = properties.get("VersioningConfiguration", {})
        if versioning.get("Status") != "Enabled":
            self.add_finding(
                Finding(
                    severity=FindingSeverity.INFO,
                    code="S3_NO_VERSIONING",
                    message="S3 bucket has no versioning enabled",
                    resource=resource_id,
                )
            )

    # --- Security Group Checks ---

    def _check_security_group(
        self, stack_name: str, logical_id: str, properties: dict[str, Any]
    ) -> None:
        """Check security group configuration."""
        resource_id = f"{stack_name}/{logical_id}"

        ingress_rules = properties.get("SecurityGroupIngress", [])

        for rule in ingress_rules:
            cidr = rule.get("CidrIp", "")
            cidr_v6 = rule.get("CidrIpv6", "")

            # Check for open to world
            if cidr == "0.0.0.0/0" or cidr_v6 == "::/0":
                from_port = rule.get("FromPort", 0)
                to_port = rule.get("ToPort", 65535)

                # SSH open to world is critical
                if from_port <= 22 <= to_port:
                    self.add_finding(
                        Finding(
                            severity=FindingSeverity.CRITICAL,
                            code="SG_SSH_OPEN",
                            message="Security group allows SSH (22) from 0.0.0.0/0",
                            resource=resource_id,
                            remediation="Restrict SSH access to specific IP ranges",
                        )
                    )

                # RDP open to world is critical
                if from_port <= 3389 <= to_port:
                    self.add_finding(
                        Finding(
                            severity=FindingSeverity.CRITICAL,
                            code="SG_RDP_OPEN",
                            message="Security group allows RDP (3389) from 0.0.0.0/0",
                            resource=resource_id,
                            remediation="Restrict RDP access to specific IP ranges",
                        )
                    )

                # Database ports open to world is critical
                db_ports = [5432, 3306, 1433, 27017, 6379]
                for db_port in db_ports:
                    if from_port <= db_port <= to_port:
                        self.add_finding(
                            Finding(
                                severity=FindingSeverity.CRITICAL,
                                code="SG_DB_OPEN",
                                message=f"Security group allows database port {db_port} from 0.0.0.0/0",
                                resource=resource_id,
                                remediation="Restrict database access to VPC CIDR only",
                            )
                        )

    # --- ECS Checks ---

    def _check_ecs_task(self, stack_name: str, logical_id: str, properties: dict[str, Any]) -> None:
        """Check ECS task definition configuration."""
        resource_id = f"{stack_name}/{logical_id}"

        container_defs = properties.get("ContainerDefinitions", [])

        for container in container_defs:
            container_name = container.get("Name", "unknown")

            # Check for privileged mode
            if container.get("Privileged", False):
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.HIGH,
                        code="ECS_PRIVILEGED",
                        message=f"Container '{container_name}' runs in privileged mode",
                        resource=resource_id,
                        remediation="Remove Privileged setting unless absolutely necessary",
                    )
                )

            # Check for root user
            user = container.get("User", "")
            if user == "root" or user == "0":
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.WARN,
                        code="ECS_ROOT_USER",
                        message=f"Container '{container_name}' runs as root",
                        resource=resource_id,
                        remediation="Use a non-root user",
                    )
                )

            # Check for read-only root filesystem
            if not container.get("ReadonlyRootFilesystem", False):
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.INFO,
                        code="ECS_WRITABLE_ROOT",
                        message=f"Container '{container_name}' has writable root filesystem",
                        resource=resource_id,
                        remediation="Consider setting ReadonlyRootFilesystem to true",
                    )
                )

            # Check for secrets in environment variables
            env_vars = container.get("Environment", [])
            sensitive_patterns = ["PASSWORD", "SECRET", "KEY", "TOKEN", "CREDENTIAL"]
            for env in env_vars:
                name = env.get("Name", "")
                value = env.get("Value", "")
                for pattern in sensitive_patterns:
                    if pattern in name.upper() and value and not value.startswith("{{"):
                        self.add_finding(
                            Finding(
                                severity=FindingSeverity.CRITICAL,
                                code="ECS_SECRET_IN_ENV",
                                message=f"Possible secret in environment variable: {name}",
                                resource=resource_id,
                                remediation="Use Secrets Manager or Parameter Store instead",
                            )
                        )

    # --- IAM Checks ---

    def _check_iam_role(self, stack_name: str, logical_id: str, properties: dict[str, Any]) -> None:
        """Check IAM role configuration."""
        resource_id = f"{stack_name}/{logical_id}"

        # Check assume role policy
        assume_policy = properties.get("AssumeRolePolicyDocument", {})
        statements = assume_policy.get("Statement", [])

        for statement in statements:
            principal = statement.get("Principal", {})
            if principal == "*":
                self.add_finding(
                    Finding(
                        severity=FindingSeverity.CRITICAL,
                        code="IAM_ROLE_WILDCARD_PRINCIPAL",
                        message="IAM role can be assumed by anyone",
                        resource=resource_id,
                        remediation="Specify explicit principals",
                    )
                )

        # Check inline policies
        policies = properties.get("Policies", [])
        for policy in policies:
            self._check_policy_document(stack_name, logical_id, policy.get("PolicyDocument", {}))

    def _check_iam_policy(
        self, stack_name: str, logical_id: str, properties: dict[str, Any]
    ) -> None:
        """Check IAM policy configuration."""
        policy_doc = properties.get("PolicyDocument", {})
        self._check_policy_document(stack_name, logical_id, policy_doc)

    def _check_policy_document(
        self, stack_name: str, logical_id: str, policy_doc: dict[str, Any]
    ) -> None:
        """Check IAM policy document for dangerous permissions."""
        resource_id = f"{stack_name}/{logical_id}"
        statements = policy_doc.get("Statement", [])

        for statement in statements:
            effect = statement.get("Effect", "Allow")
            actions = statement.get("Action", [])
            resources = statement.get("Resource", [])

            if effect != "Allow":
                continue

            # Normalize to lists
            if isinstance(actions, str):
                actions = [actions]
            if isinstance(resources, str):
                resources = [resources]

            # Check for admin privileges
            if "*" in actions or "iam:*" in actions:
                if "*" in resources:
                    self.add_finding(
                        Finding(
                            severity=FindingSeverity.CRITICAL,
                            code="IAM_ADMIN_ACCESS",
                            message="Policy grants administrative access",
                            resource=resource_id,
                            remediation="Use least-privilege permissions",
                        )
                    )

            # Check for specific dangerous permissions
            dangerous_actions = [
                "iam:CreateUser",
                "iam:AttachUserPolicy",
                "iam:AttachRolePolicy",
                "iam:PutUserPolicy",
                "iam:PutRolePolicy",
                "sts:AssumeRole",
            ]

            for action in actions:
                if action in dangerous_actions and "*" in resources:
                    self.add_finding(
                        Finding(
                            severity=FindingSeverity.HIGH,
                            code="IAM_DANGEROUS_PERMISSION",
                            message=f"Policy grants dangerous permission: {action}",
                            resource=resource_id,
                            remediation="Restrict to specific resources",
                        )
                    )

    # --- Lambda Checks ---

    def _check_lambda_function(
        self, stack_name: str, logical_id: str, properties: dict[str, Any]
    ) -> None:
        """Check Lambda function configuration."""
        resource_id = f"{stack_name}/{logical_id}"

        # Check for VPC configuration
        vpc_config = properties.get("VpcConfig")
        if not vpc_config:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.INFO,
                    code="LAMBDA_NO_VPC",
                    message="Lambda function is not in a VPC",
                    resource=resource_id,
                )
            )

        # Check for reserved concurrency (DoS protection)
        if not properties.get("ReservedConcurrentExecutions"):
            self.add_finding(
                Finding(
                    severity=FindingSeverity.INFO,
                    code="LAMBDA_NO_RESERVED_CONCURRENCY",
                    message="Lambda has no reserved concurrency limit",
                    resource=resource_id,
                    remediation="Consider setting ReservedConcurrentExecutions",
                )
            )

    # --- SQS Checks ---

    def _check_sqs_queue(
        self, stack_name: str, logical_id: str, properties: dict[str, Any]
    ) -> None:
        """Check SQS queue configuration."""
        resource_id = f"{stack_name}/{logical_id}"

        # Check for encryption
        kms_key = properties.get("KmsMasterKeyId")
        sqs_managed = properties.get("SqsManagedSseEnabled", False)

        if not kms_key and not sqs_managed:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.WARN,
                    code="SQS_NOT_ENCRYPTED",
                    message="SQS queue has no encryption configured",
                    resource=resource_id,
                    remediation="Enable SQS managed SSE or use a KMS key",
                )
            )

        # Check for dead letter queue
        redrive = properties.get("RedrivePolicy")
        if not redrive:
            self.add_finding(
                Finding(
                    severity=FindingSeverity.INFO,
                    code="SQS_NO_DLQ",
                    message="SQS queue has no dead letter queue",
                    resource=resource_id,
                    remediation="Configure a dead letter queue for failed messages",
                )
            )
