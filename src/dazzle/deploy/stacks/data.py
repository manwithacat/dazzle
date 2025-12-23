"""
Data stack generator.

Generates RDS (Postgres) and S3 bucket resources.
"""

from __future__ import annotations

from ..generator import CDKGeneratorResult, StackGenerator


class DataStackGenerator(StackGenerator):
    """Generate data layer resources (RDS, S3)."""

    @property
    def stack_name(self) -> str:
        return "Data"

    def should_generate(self) -> bool:
        """Only generate if database or storage is needed."""
        return self.aws_reqs.needs_rds or self.aws_reqs.needs_s3

    def _generate_stack_code(self) -> str:
        """Generate the data stack Python code."""
        # Build imports based on what's needed
        imports = ["from aws_cdk import aws_ec2 as ec2"]
        if self.aws_reqs.needs_rds:
            imports.append("from aws_cdk import aws_rds as rds")
            imports.append("from aws_cdk import aws_secretsmanager as secretsmanager")
        if self.aws_reqs.needs_s3:
            imports.append("from aws_cdk import aws_s3 as s3")

        imports_code = "\n".join(imports)

        # Generate RDS code
        rds_code = self._generate_rds_code() if self.aws_reqs.needs_rds else ""

        # Generate S3 code
        s3_code = self._generate_s3_code() if self.aws_reqs.needs_s3 else ""

        # Generate outputs
        outputs_code = self._generate_outputs_code()

        return f'''{self._generate_header()}
{imports_code}


class DataStack(Stack):
    """
    Data layer resources for {self.spec.name}.

    Creates:
    {"- Aurora Serverless v2 PostgreSQL cluster" if self.aws_reqs.needs_rds and self.config.database.is_serverless else "- RDS PostgreSQL instance" if self.aws_reqs.needs_rds else ""}
    {"- S3 bucket for assets" if self.aws_reqs.needs_s3 else ""}
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        network_stack,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.network_stack = network_stack
{rds_code}
{s3_code}
{outputs_code}
'''

    def _generate_rds_code(self) -> str:
        """Generate RDS/Aurora code."""
        app_name = self._get_app_name()
        env = self.config.environment
        db_name = app_name.replace("-", "_")

        if self.config.database.is_serverless:
            return self._generate_aurora_serverless_code(app_name, env, db_name)
        else:
            return self._generate_rds_instance_code(app_name, env, db_name)

    def _generate_aurora_serverless_code(self, app_name: str, env: str, db_name: str) -> str:
        """Generate Aurora Serverless v2 code."""
        backup_days = self.config.database.backup_retention_days
        deletion_protection = str(self.config.database.deletion_protection).lower()

        return f'''
        # =====================================================================
        # Aurora Serverless v2 (PostgreSQL)
        # =====================================================================

        self.database = rds.DatabaseCluster(
            self,
            "Database",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_4,
            ),
            serverless_v2_min_capacity=0.5,
            serverless_v2_max_capacity=4,
            writer=rds.ClusterInstance.serverless_v2(
                "Writer",
                scale_with_writer=True,
            ),
            vpc=network_stack.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
            ),
            security_groups=[network_stack.rds_security_group],
            credentials=rds.Credentials.from_generated_secret(
                "postgres",
                secret_name="{app_name}-{env}-db-credentials",
            ),
            default_database_name="{db_name}",
            backup=rds.BackupProps(
                retention=Duration.days({backup_days}),
            ),
            deletion_protection={deletion_protection},
            removal_policy=RemovalPolicy.{"RETAIN" if self.config.database.deletion_protection else "DESTROY"},
            storage_encrypted=True,
        )

        # Database connection info for ECS
        self.database_secret = self.database.secret
        self.database_url = f"postgresql://{{{{self.database.secret.secret_value_from_json('username').unsafe_unwrap()}}}}:{{{{self.database.secret.secret_value_from_json('password').unsafe_unwrap()}}}}@{{{{self.database.cluster_endpoint.hostname}}}}:5432/{db_name}"
'''

    def _generate_rds_instance_code(self, app_name: str, env: str, db_name: str) -> str:
        """Generate RDS instance code."""
        instance_type = self.config.database.size.value
        multi_az = str(self.config.database.multi_az).lower()
        backup_days = self.config.database.backup_retention_days
        deletion_protection = str(self.config.database.deletion_protection).lower()

        return f'''
        # =====================================================================
        # RDS PostgreSQL Instance
        # =====================================================================

        self.database = rds.DatabaseInstance(
            self,
            "Database",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_15,
            ),
            instance_type=ec2.InstanceType("{instance_type}"),
            vpc=network_stack.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
            ),
            security_groups=[network_stack.rds_security_group],
            credentials=rds.Credentials.from_generated_secret(
                "postgres",
                secret_name="{app_name}-{env}-db-credentials",
            ),
            database_name="{db_name}",
            multi_az={multi_az},
            allocated_storage=20,
            max_allocated_storage=100,
            backup_retention=Duration.days({backup_days}),
            deletion_protection={deletion_protection},
            removal_policy=RemovalPolicy.{"RETAIN" if self.config.database.deletion_protection else "DESTROY"},
            storage_encrypted=True,
        )

        # Database connection info for ECS
        self.database_secret = self.database.secret
        self.database_url = f"postgresql://{{{{self.database.secret.secret_value_from_json('username').unsafe_unwrap()}}}}:{{{{self.database.secret.secret_value_from_json('password').unsafe_unwrap()}}}}@{{{{self.database.db_instance_endpoint_address}}}}:5432/{db_name}"
'''

    def _generate_s3_code(self) -> str:
        """Generate S3 bucket code."""
        app_name = self._get_app_name()
        env = self.config.environment
        versioned = str(self.config.storage.versioned).lower()

        lifecycle_rule = ""
        if self.config.storage.lifecycle_expiration_days:
            days = self.config.storage.lifecycle_expiration_days
            lifecycle_rule = f"""
            lifecycle_rules=[
                s3.LifecycleRule(
                    expiration=Duration.days({days}),
                ),
            ],"""

        return f'''
        # =====================================================================
        # S3 Bucket for Assets
        # =====================================================================

        self.assets_bucket = s3.Bucket(
            self,
            "AssetsBucket",
            bucket_name="{app_name}-{env}-assets",
            versioned={versioned},
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,{lifecycle_rule}
            cors=[
                s3.CorsRule(
                    allowed_methods=[
                        s3.HttpMethods.GET,
                        s3.HttpMethods.PUT,
                        s3.HttpMethods.POST,
                    ],
                    allowed_origins={self.config.storage.cors_allowed_origins},
                    allowed_headers=["*"],
                    max_age=3600,
                ),
            ],
        )
'''

    def _generate_outputs_code(self) -> str:
        """Generate CloudFormation outputs."""
        app_name = self._get_app_name()
        env = self.config.environment

        outputs = []

        if self.aws_reqs.needs_rds:
            outputs.append(f'''
        CfnOutput(
            self,
            "DatabaseEndpoint",
            value=self.database.{"cluster_endpoint.hostname" if self.config.database.is_serverless else "db_instance_endpoint_address"},
            description="Database endpoint",
            export_name="{app_name}-{env}-db-endpoint",
        )

        CfnOutput(
            self,
            "DatabaseSecretArn",
            value=self.database_secret.secret_arn,
            description="Database credentials secret ARN",
            export_name="{app_name}-{env}-db-secret-arn",
        )''')

        if self.aws_reqs.needs_s3:
            outputs.append(f'''
        CfnOutput(
            self,
            "AssetsBucketName",
            value=self.assets_bucket.bucket_name,
            description="Assets bucket name",
            export_name="{app_name}-{env}-assets-bucket",
        )

        CfnOutput(
            self,
            "AssetsBucketArn",
            value=self.assets_bucket.bucket_arn,
            description="Assets bucket ARN",
        )''')

        return "\n".join(outputs) if outputs else ""

    def generate(self) -> CDKGeneratorResult:
        """Generate the data stack and record artifacts."""
        result = super().generate()

        if result.success and self.should_generate():
            artifacts = {}
            if self.aws_reqs.needs_rds:
                # Stack reference names, not actual secrets
                artifacts["database_secret_ref"] = "data_stack.database_secret"  # nosec B105
                artifacts["database_url_ref"] = "data_stack.database_url"
            if self.aws_reqs.needs_s3:
                artifacts["assets_bucket_ref"] = "data_stack.assets_bucket"

            result.add_artifact("data_stack", artifacts)

        return result
