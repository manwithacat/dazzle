"""
Infrastructure requirements analyzer for DAZZLE.

Analyzes AppSpec IR to infer infrastructure needs without requiring
explicit infrastructure declarations in the DSL.
"""

from dataclasses import dataclass
from typing import List

from . import ir


@dataclass
class InfraRequirements:
    """
    Infrastructure requirements inferred from AppSpec.

    This represents what infrastructure components are needed based on
    the application's domain model, services, and integrations.
    """
    # Core infrastructure
    needs_database: bool = False
    needs_cache: bool = False
    needs_queue: bool = False
    needs_workers: bool = False
    needs_webhooks: bool = False
    needs_storage: bool = False

    # Type specifications
    database_type: str = "postgres"
    cache_type: str = "redis"
    queue_type: str = "redis"  # or "sqs", "pubsub"
    storage_type: str = "s3"   # or "gcs", "blob"

    # Detailed requirements
    entity_count: int = 0
    service_count: int = 0
    integration_count: int = 0
    experience_count: int = 0
    surface_count: int = 0

    # Specific needs
    entity_names: List[str] = None
    webhook_service_names: List[str] = None
    async_service_names: List[str] = None

    def __post_init__(self):
        """Initialize lists if None."""
        if self.entity_names is None:
            self.entity_names = []
        if self.webhook_service_names is None:
            self.webhook_service_names = []
        if self.async_service_names is None:
            self.async_service_names = []

    def has_any_infra_needs(self) -> bool:
        """Check if any infrastructure is needed."""
        return (
            self.needs_database
            or self.needs_cache
            or self.needs_queue
            or self.needs_workers
            or self.needs_webhooks
            or self.needs_storage
        )


def analyze_infra_requirements(appspec: ir.AppSpec) -> InfraRequirements:
    """
    Analyze AppSpec IR to determine infrastructure requirements.

    Logic:
    - Entities → database required
    - Services with integrations → cache recommended
    - Experiences or async patterns → queue + workers
    - Webhook services → inbound routing
    - File/media fields → object storage

    Args:
        appspec: The application specification from IR

    Returns:
        InfraRequirements describing needed infrastructure
    """
    requirements = InfraRequirements()

    # Analyze entities
    if appspec.domain.entities:
        requirements.needs_database = True
        requirements.entity_count = len(appspec.domain.entities)
        requirements.entity_names = [e.name for e in appspec.domain.entities]

        # Check for file/media fields that need storage
        for entity in appspec.domain.entities:
            for field in entity.fields:
                # Check if field type suggests file storage
                field_type_str = str(field.type).lower()
                if any(keyword in field_type_str for keyword in ["file", "media", "image", "document"]):
                    requirements.needs_storage = True
                    break

    # Analyze services
    requirements.service_count = len(appspec.services)
    if appspec.services:
        for service in appspec.services:
            service_type = getattr(service, "service_type", "").lower()

            # Webhook services need inbound routing
            if "webhook" in service_type:
                requirements.needs_webhooks = True
                requirements.webhook_service_names.append(service.name)

            # Async/background services need queue + workers
            if any(keyword in service_type for keyword in ["async", "background", "queue", "job"]):
                requirements.needs_queue = True
                requirements.needs_workers = True
                requirements.async_service_names.append(service.name)

    # Analyze integrations
    requirements.integration_count = len(appspec.integrations)
    if appspec.integrations:
        # Integrations benefit from caching
        requirements.needs_cache = True

        # Many integrations suggest async processing
        if len(appspec.integrations) > 2:
            requirements.needs_queue = True
            requirements.needs_workers = True

    # Analyze experiences (multi-step workflows)
    requirements.experience_count = len(appspec.experiences)
    if appspec.experiences:
        # Experiences often need session/state caching
        requirements.needs_cache = True

        # Complex experiences may need async processing
        if len(appspec.experiences) > 1:
            requirements.needs_queue = True
            requirements.needs_workers = True

    # Analyze surfaces (for counting)
    requirements.surface_count = len(appspec.surfaces)

    return requirements


def get_required_env_vars(requirements: InfraRequirements) -> List[str]:
    """
    Get list of environment variables needed based on requirements.

    Args:
        requirements: Infrastructure requirements

    Returns:
        List of environment variable names
    """
    env_vars = []

    if requirements.needs_database:
        env_vars.extend([
            "DATABASE_URL",
            "DATABASE_HOST",
            "DATABASE_PORT",
            "DATABASE_NAME",
            "DATABASE_USER",
            "DATABASE_PASSWORD",
        ])

    if requirements.needs_cache:
        env_vars.extend([
            "REDIS_URL",
            "REDIS_HOST",
            "REDIS_PORT",
        ])

    if requirements.needs_queue:
        env_vars.extend([
            "QUEUE_URL",
            "WORKER_CONCURRENCY",
        ])

    if requirements.needs_storage:
        env_vars.extend([
            "STORAGE_BUCKET",
            "STORAGE_REGION",
            "STORAGE_ACCESS_KEY",
            "STORAGE_SECRET_KEY",
        ])

    if requirements.needs_webhooks:
        env_vars.extend([
            "WEBHOOK_SECRET",
            "WEBHOOK_URL",
        ])

    # Always include common vars
    env_vars.extend([
        "APP_ENV",
        "APP_DEBUG",
        "SECRET_KEY",
    ])

    return env_vars


__all__ = [
    "InfraRequirements",
    "analyze_infra_requirements",
    "get_required_env_vars",
]
