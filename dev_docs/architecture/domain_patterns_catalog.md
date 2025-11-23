# Domain Patterns Catalog - Intent-Level Vocabulary

**Created**: 2025-11-23
**Status**: Prototype/Proposal
**Purpose**: Catalog of cross-stack domain patterns for core vocabulary

This catalog contains **intent-level** patterns that express business requirements without prescribing implementation details. Each pattern can be implemented idiomatically across Django, Express, FastAPI, Next.js, GraphQL, and serverless stacks.

## Pattern Categories

1. **Operations** - What the system can do with data
2. **Workflows** - How data changes state over time
3. **Cross-Cutting** - Concerns that apply across entities
4. **Integration** - How systems connect

---

## 1. Operations Patterns

### crud_operations

**Intent**: Entity supports Create, Read, Update, Delete, and List operations

**Use Cases**: Any entity users can manage
- Task lists, product catalogs, user profiles
- Inventory management, content management
- Any CRUD application

**Parameters**:
```yaml
- entity_name: string (required)
- soft_delete: boolean (default: false)
- audit_trail: boolean (default: true)
- bulk_operations: boolean (default: false)
```

**Hints**:
```yaml
generates: [create, read, update, delete, list]
permissions: per_operation
validation: on_create_and_update
```

**Stack Interpretations**:
| Stack | Implementation |
|-------|----------------|
| Django | Admin + ModelForm + ListView/DetailView/CreateView/UpdateView/DeleteView |
| Express | Routes + Controller + Service + Repository for each operation |
| FastAPI | Routes with dependencies, CRUD service, Pydantic schemas |
| Next.js | API routes + Server actions + Client components |
| GraphQL | Queries (read, list) + Mutations (create, update, delete) + Resolvers |
| OpenAPI | Paths for GET/POST/PUT/DELETE with schemas |

**Usage**:
```dsl
entity Task:
  @use crud_operations(soft_delete=true, audit_trail=true)
```

---

### search_operations

**Intent**: Entity supports search, filtering, and sorting

**Use Cases**: Finding items in large datasets
- Product search, user lookup, log filtering
- Full-text search, faceted search
- Any searchable collection

**Parameters**:
```yaml
- search_fields: list (required) - Fields for text search
- filter_fields: list (optional) - Fields for exact filtering
- sort_fields: list (optional) - Fields for sorting
- full_text: boolean (default: false) - Use full-text search engine
- fuzzy: boolean (default: false) - Allow fuzzy matching
```

**Hints**:
```yaml
indexing: required
query_optimization: true
pagination: cursor_or_offset
```

**Stack Interpretations**:
| Stack | Implementation |
|-------|----------------|
| Django | QuerySet filters, Q objects, full_text search (Postgres) |
| Express | Query params, Sequelize where clauses, Elasticsearch |
| FastAPI | Query params, SQLAlchemy filters, dependencies |
| Next.js | API route params, Prisma filters |
| GraphQL | Query args, field resolvers, Dataloader batching |
| OpenAPI | Query parameters in schema |

**Usage**:
```dsl
entity Product:
  @use search_operations(
    search_fields=[name, description],
    filter_fields=[category, price_range, in_stock],
    sort_fields=[name, price, created_at],
    full_text=true
  )
```

---

### export_operations

**Intent**: Entity data can be exported in various formats

**Use Cases**: Reporting, data portability, backups
- Export to CSV, JSON, Excel
- Data migration, integration with other tools
- Compliance (GDPR data export)

**Parameters**:
```yaml
- formats: list (default: [csv, json]) - Export formats
- fields: list (optional) - Fields to include (default: all)
- filtered: boolean (default: true) - Apply search filters to export
- scheduled: boolean (default: false) - Support scheduled exports
```

**Hints**:
```yaml
streaming: for_large_datasets
async: if_scheduled
storage: temporary_or_s3
```

**Stack Interpretations**:
| Stack | Implementation |
|-------|----------------|
| Django | Management command, view with StreamingHttpResponse |
| Express | Route with stream, csv/xlsx libraries |
| FastAPI | Background task, streaming response |
| Next.js | API route with stream, lib for format conversion |
| GraphQL | Query with format arg, streaming if supported |
| OpenAPI | Endpoint with Accept header for formats |

**Usage**:
```dsl
entity Order:
  @use export_operations(
    formats=[csv, excel, json],
    filtered=true,
    scheduled=true
  )
```

---

## 2. Workflow Patterns

### status_workflow

**Intent**: Entity progresses through defined states with valid transitions

**Use Cases**: Lifecycle management, approval processes
- Order processing (Draft → Submitted → Approved → Shipped)
- Content publishing (Draft → Review → Published → Archived)
- Ticket resolution (Open → InProgress → Resolved → Closed)

**Parameters**:
```yaml
- states: list (required) - All possible states
- initial_state: string (required) - Starting state
- transitions: list (optional) - Explicit transitions (if not, all allowed)
- final_states: list (optional) - Terminal states (can't transition from)
```

**Hints**:
```yaml
validation: enforce_transitions
audit: track_all_transitions
notifications: on_state_change
rollback: support_if_possible
```

**Stack Interpretations**:
| Stack | Implementation |
|-------|----------------|
| Django | django-fsm or enum field with validation |
| Express | State machine library, validation middleware |
| FastAPI | Pydantic validation, state transition endpoints |
| Next.js | State in DB, validation in API routes |
| GraphQL | Enum type, mutation with validation |
| OpenAPI | Enum schema, transition endpoints |

**Usage**:
```dsl
entity Order:
  @use status_workflow(
    states=[Draft, Submitted, Approved, Processing, Shipped, Delivered, Cancelled],
    initial_state=Draft,
    transitions=[
      Draft->Submitted,
      Submitted->Approved,
      Submitted->Cancelled,
      Approved->Processing,
      Processing->Shipped,
      Shipped->Delivered
    ],
    final_states=[Delivered, Cancelled]
  )
```

---

### approval_workflow

**Intent**: Entity requires multi-step approval before activation

**Use Cases**: Multi-level authorization
- Expense approval (Manager → Director → Finance)
- Content review (Editor → Legal → Publisher)
- Access requests (Team Lead → Security → Admin)

**Parameters**:
```yaml
- steps: list (required) - Approval steps in order
- approver_roles: list (required) - Roles that can approve
- rejection_handling: string (default: restart) - restart|previous|cancel
- parallel: boolean (default: false) - Steps can approve in parallel
```

**Hints**:
```yaml
notifications: notify_next_approver
audit: track_all_decisions
delegation: support_if_needed
timeout: configurable_sla
```

**Stack Interpretations**:
| Stack | Implementation |
|-------|----------------|
| Django | Approval model, signals for notifications |
| Express | Approval table, event emitter for notifications |
| FastAPI | Background tasks for notifications, DB for state |
| Next.js | Server actions, email/notification service |
| GraphQL | Mutations for approve/reject, subscriptions for updates |
| OpenAPI | Approval endpoints, webhook callbacks |

**Usage**:
```dsl
entity PurchaseOrder:
  @use approval_workflow(
    steps=[ManagerReview, DirectorReview, FinanceApproval],
    approver_roles=[Manager, Director, Finance],
    rejection_handling=restart,
    parallel=false
  )
```

---

### scheduled_workflow

**Intent**: Entity triggers actions at scheduled times

**Use Cases**: Time-based automation
- Recurring tasks, scheduled reports
- Subscription renewals, payment processing
- Data cleanup, cache invalidation

**Parameters**:
```yaml
- schedule_type: string (required) - cron|interval|once
- schedule_spec: string (required) - Cron expression or interval
- action: string (required) - Action to perform
- timezone: string (default: UTC)
```

**Hints**:
```yaml
scheduler: background_job
retry: on_failure
concurrency: prevent_overlaps
```

**Stack Interpretations**:
| Stack | Implementation |
|-------|----------------|
| Django | Celery beat, APScheduler, Django Q |
| Express | node-cron, Bull queue, Agenda |
| FastAPI | APScheduler, Celery, background tasks |
| Next.js | Vercel cron, external scheduler |
| Serverless | EventBridge, CloudWatch Events, Step Functions |

**Usage**:
```dsl
entity Report:
  @use scheduled_workflow(
    schedule_type=cron,
    schedule_spec="0 8 * * 1",  # Every Monday at 8am
    action=generate_weekly_report,
    timezone=America/Los_Angeles
  )
```

---

## 3. Cross-Cutting Patterns

### audit_trail

**Intent**: Track all changes with who/when/what

**Use Cases**: Compliance, debugging, accountability
- Who changed what and when
- GDPR/SOX compliance
- Security auditing, fraud detection

**Parameters**:
```yaml
- track_creates: boolean (default: true)
- track_updates: boolean (default: true)
- track_deletes: boolean (default: true)
- track_reads: boolean (default: false)
- retention_days: int (optional) - How long to keep audit logs
```

**Hints**:
```yaml
storage: append_only
performance: async_logging
querying: indexed_by_entity_and_time
```

**Stack Interpretations**:
| Stack | Implementation |
|-------|----------------|
| Django | django-auditlog, signals, AuditLog model |
| Express | Audit middleware, separate audit table |
| FastAPI | Dependency injection, audit service |
| Next.js | Middleware, audit API endpoints |
| GraphQL | Plugin/extension for all mutations |
| DynamoDB | Streams to audit table |

**Usage**:
```dsl
entity SensitiveData:
  @use audit_trail(
    track_creates=true,
    track_updates=true,
    track_deletes=true,
    track_reads=true,
    retention_days=2555  # 7 years for compliance
  )
```

---

### soft_delete

**Intent**: Mark records as deleted without removing from database

**Use Cases**: Recoverability, legal hold, data retention
- Trash/recycle bin functionality
- Compliance (can't permanently delete)
- Undo capability

**Parameters**:
```yaml
- field_name: string (default: deleted_at)
- include_user: boolean (default: true) - Track who deleted
- default_scope: string (default: exclude) - exclude|include
- permanent_delete: boolean (default: false) - Allow hard delete
```

**Hints**:
```yaml
default_queries: exclude_deleted
recovery: admin_interface
cleanup: scheduled_purge_after_retention
```

**Stack Interpretations**:
| Stack | Implementation |
|-------|----------------|
| Django | Custom manager with default exclude filter |
| Express | Global scope on model, soft delete method |
| FastAPI | Filter dependency, soft delete service method |
| Next.js | Middleware to filter, soft delete API |
| GraphQL | Filter in dataloader, soft delete mutation |
| DynamoDB | Filter expression, mark deleted attribute |

**Usage**:
```dsl
entity Document:
  @use soft_delete(
    field_name=deleted_at,
    include_user=true,
    default_scope=exclude,
    permanent_delete=false
  )
```

---

### multi_tenant

**Intent**: Isolate data by tenant/organization

**Use Cases**: SaaS applications, multi-org platforms
- Each customer sees only their data
- Row-level isolation
- Tenant-scoped queries

**Parameters**:
```yaml
- tenant_field: string (default: organization_id)
- isolation_level: string (default: row) - row|schema|database
- default_scope: string (default: current_tenant)
```

**Hints**:
```yaml
context: from_request_or_session
migration: per_tenant_or_shared
indexing: include_tenant_in_all_indexes
```

**Stack Interpretations**:
| Stack | Implementation |
|-------|----------------|
| Django | Middleware to set tenant, manager to scope queries |
| Express | Middleware to inject tenant_id, query scoping |
| FastAPI | Depends to get tenant, query filter |
| Next.js | Session/auth context, query scoping |
| GraphQL | Context with tenant, dataloader scoping |
| DynamoDB | Partition key or filter expression |

**Usage**:
```dsl
entity Project:
  @use multi_tenant(
    tenant_field=organization_id,
    isolation_level=row,
    default_scope=current_tenant
  )
```

---

### rate_limiting

**Intent**: Limit operation frequency to prevent abuse

**Use Cases**: API protection, resource management
- Prevent DDoS, brute force attacks
- Fair usage in SaaS, cost control
- Quality of service guarantees

**Parameters**:
```yaml
- operations: list (required) - Operations to limit
- rate: string (required) - "X per Y" (e.g., "100 per hour")
- scope: string (default: user) - user|ip|api_key|global
- strategy: string (default: sliding_window)
```

**Hints**:
```yaml
storage: redis_or_in_memory
response: 429_with_retry_after
bypass: for_admin_or_internal
```

**Stack Interpretations**:
| Stack | Implementation |
|-------|----------------|
| Django | django-ratelimit decorator on views |
| Express | express-rate-limit middleware |
| FastAPI | slowapi or custom dependency |
| Next.js | Middleware with rate limit check |
| GraphQL | Plugin for query complexity and rate limiting |
| API Gateway | Built-in rate limiting |

**Usage**:
```dsl
entity APIEndpoint:
  @use rate_limiting(
    operations=[create, update, delete],
    rate="100 per hour",
    scope=user,
    strategy=sliding_window
  )
```

---

## 4. Integration Patterns

### webhook_integration

**Intent**: Send HTTP callbacks when events occur

**Use Cases**: Event notification, system integration
- Notify external systems of changes
- Trigger workflows in other services
- Real-time data sync

**Parameters**:
```yaml
- events: list (required) - Events that trigger webhooks
- retry_policy: string (default: exponential_backoff)
- timeout: int (default: 30) - Request timeout in seconds
- security: string (default: hmac) - hmac|oauth|none
```

**Hints**:
```yaml
delivery: async_queue
dead_letter: after_max_retries
monitoring: log_all_attempts
```

**Stack Interpretations**:
| Stack | Implementation |
|-------|----------------|
| Django | Celery task, django-rest-hooks |
| Express | Queue (Bull/Bee), axios for HTTP |
| FastAPI | Background task, httpx for async |
| Next.js | Queue or serverless function |
| Serverless | EventBridge, Lambda, SNS |

**Usage**:
```dsl
entity Order:
  @use webhook_integration(
    events=[created, status_changed, cancelled],
    retry_policy=exponential_backoff,
    timeout=30,
    security=hmac
  )
```

---

## Usage Examples

### E-Commerce Order (Complex)

```dsl
entity Order "Order":
  id: uuid pk
  customer: ref Customer required
  total: decimal(10,2) required

  # Operations
  @use crud_operations(soft_delete=true, audit_trail=true)
  @use search_operations(
    search_fields=[order_number, customer_name],
    filter_fields=[status, created_at, total],
    sort_fields=[created_at, total]
  )
  @use export_operations(formats=[csv, excel])

  # Workflows
  @use status_workflow(
    states=[Draft, Submitted, Approved, Processing, Shipped, Delivered, Cancelled],
    initial_state=Draft,
    final_states=[Delivered, Cancelled]
  )

  # Cross-cutting
  @use multi_tenant(tenant_field=merchant_id)
  @use rate_limiting(
    operations=[create],
    rate="10 per minute",
    scope=user
  )

  # Integration
  @use webhook_integration(
    events=[status_changed, delivered],
    security=hmac
  )
```

### SaaS Project (Multi-Tenant)

```dsl
entity Project "Project":
  id: uuid pk
  name: str(200) required

  # Multi-tenancy
  @use multi_tenant(
    tenant_field=organization_id,
    isolation_level=row
  )

  # Operations
  @use crud_operations(soft_delete=true, audit_trail=true)
  @use search_operations(
    search_fields=[name, description],
    filter_fields=[status, owner]
  )

  # Workflows
  @use status_workflow(
    states=[Active, Archived, Deleted],
    initial_state=Active
  )

  # Cross-cutting
  @use rate_limiting(
    operations=[create],
    rate="100 per day",
    scope=organization
  )
```

### Content Management (Approval)

```dsl
entity Article "Article":
  id: uuid pk
  title: str(200) required
  content: text required

  # Operations
  @use crud_operations(audit_trail=true)
  @use search_operations(
    search_fields=[title, content],
    full_text=true
  )

  # Workflows
  @use status_workflow(
    states=[Draft, InReview, Published, Archived],
    initial_state=Draft
  )
  @use approval_workflow(
    steps=[EditorReview, LegalReview],
    approver_roles=[Editor, Legal],
    rejection_handling=restart
  )

  # Integration
  @use webhook_integration(
    events=[published, archived],
    security=oauth
  )
  @use scheduled_workflow(
    schedule_type=cron,
    schedule_spec="0 0 * * *",  # Midnight daily
    action=archive_old_drafts
  )
```

## Pattern Composition

Patterns can be composed for rich behavior:

```dsl
entity Invoice:
  # All the power
  @use crud_operations(soft_delete=true, audit_trail=true, bulk_operations=true)
  @use search_operations(search_fields=[number, customer], full_text=true)
  @use export_operations(formats=[pdf, csv, json], scheduled=true)
  @use status_workflow(states=[Draft, Sent, Paid, Overdue, Cancelled])
  @use approval_workflow(steps=[ManagerApproval, FinanceApproval])
  @use multi_tenant(tenant_field=company_id)
  @use rate_limiting(operations=[create], rate="1000 per hour")
  @use webhook_integration(events=[status_changed, paid])
```

## Next Steps

1. **Implement 3-5 patterns** in a prototype vocabulary
2. **Test with Django stack** - Verify idiomatic generation
3. **Test with Express stack** - Verify cross-stack portability
4. **Gather feedback** - Validate usefulness with real projects
5. **Iterate and expand** - Add more patterns based on demand
