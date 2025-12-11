# Task Manager with Domain Patterns
# Demonstrates intent-level vocabulary for cross-stack portability

module simple_task.patterns

app task_manager_pro "Task Manager Pro"

# User entity - simple, no patterns needed
entity User "User":
  id: uuid pk
  name: str(200) required
  email: email unique?
  @use audit_fields()

# Task entity with domain patterns
entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  priority: enum[low,medium,high]=medium

  # Domain pattern: Status workflow
  # Stack interprets this idiomatically:
  # - Django: FSM or enum with validation
  # - Express: State machine library
  # - GraphQL: Enum type with mutation validation
  @use status_workflow_pattern(
    field_name=status,
    states=[todo, in_progress, blocked, done, cancelled],
    initial_state=todo,
    track_transitions=true
  )

  # Domain pattern: Soft delete
  # Stack provides recovery mechanism:
  # - Django: Custom manager to exclude deleted
  # - Express: Global scope on model
  # - GraphQL: Filter in dataloader
  @use soft_delete_behavior(
    field_name=deleted_at,
    include_user=true
  )

  # Standard patterns
  assigned_to: ref User
  @use audit_fields()

# Project entity with multi-tenancy
entity Project "Project":
  id: uuid pk
  name: str(200) required
  description: text

  # Domain pattern: Multi-tenant isolation
  # Stack enforces tenant context:
  # - Django: Middleware + scoped manager
  # - Express: Middleware + query filter
  # - GraphQL: Context + scoped dataloader
  @use multi_tenant_isolation(
    tenant_field=organization_id,
    tenant_entity=Organization
  )

  # Domain pattern: Searchable
  # Stack implements search:
  # - Django: Postgres full-text or Elasticsearch
  # - Express: Sequelize + Elasticsearch
  # - GraphQL: Query args + optimization
  @use searchable_entity(
    search_fields=[name, description],
    filter_fields=[organization_id, created_at],
    full_text=false
  )

  @use audit_fields()

# Organization entity (for multi-tenancy)
entity Organization "Organization":
  id: uuid pk
  name: str(200) required unique
  plan: enum[free,pro,enterprise]=free
  @use audit_fields()

# Document entity with versioning
entity Document "Document":
  id: uuid pk
  title: str(200) required
  content: text required
  project: ref Project required

  # Domain pattern: Versioning
  # Stack tracks history:
  # - Django: django-simple-history
  # - Express: Versions table with FK
  # - GraphQL: Version field + history query
  @use versioned_entity(
    version_field=version,
    keep_history=true
  )

  # Domain pattern: Status workflow
  @use status_workflow_pattern(
    states=[draft, review, published, archived],
    initial_state=draft,
    track_transitions=true
  )

  @use audit_fields()

# Generate CRUD surfaces for all entities
@use crud_surface_set(entity_name=Task, title_field=title)
@use crud_surface_set(entity_name=Project, title_field=name)
@use crud_surface_set(entity_name=Organization, title_field=name)
@use crud_surface_set(entity_name=Document, title_field=title)
@use crud_surface_set(entity_name=User, title_field=name)
