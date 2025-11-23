# Vocabulary Design Philosophy - Intent vs Implementation

**Created**: 2025-11-23
**Status**: Design Proposal
**Purpose**: Define boundaries between domain vocabulary and implementation patterns

## Executive Summary

App-local vocabulary should focus on **business intent** (WHAT), not **implementation details** (HOW). This keeps the DSL portable across stacks while still providing token efficiency and guidance to LLMs.

**Core Principle**: Vocabulary entries should be answerable with "Can this be implemented idiomatically in Django, Express, FastAPI, Next.js, and GraphQL?"
- ✅ **YES** → Include in core vocabulary
- ⚠️ **PARTIALLY** → Make it more abstract or use hints
- ❌ **NO** → Move to stack-specific extensions

## The Design Tension

### The Fuzzy Boundary

```
Too Pure                    Sweet Spot                Too Specific
│                              │                            │
Domain concepts only     Intent + Hints         Implementation patterns
No guidance              Stack interprets       Stack locked-in
Slow, ambiguous         Fast, clear            Brittle, non-portable
```

### Goals to Balance

1. **Token Efficiency** - Fewer tokens to express intent
2. **Constrain Ambiguity** - Reduce LLM interpretation variance
3. **Speed of Implementation** - Faster code generation
4. **Separation of Concerns** - Good architecture emerges naturally
5. **Portability** - Works across different stacks
6. **Future-Proofing** - Adaptable to new patterns and stacks

## Three-Layer Model

### Layer 1: Core Domain Vocabulary (Intent)

**What Belongs Here**:
- Business operations (CRUD, search, export, approval)
- Domain state machines (status workflows, lifecycles)
- Cross-cutting concerns (audit, soft-delete, multi-tenancy)
- Business requirements (caching, rate-limiting, access control)

**What Does NOT Belong**:
- Implementation patterns (Controller-Service-Repository, Factory, Observer)
- Framework specifics (Django forms, Express middleware, React hooks)
- Architecture decisions (monolith, microservices, serverless)
- Technology choices (REST, GraphQL, gRPC)

**Examples**:
```yaml
# ✅ GOOD - Domain intent
- crud_operations          # Business needs CRUD, stack decides how
- status_workflow         # Business state machine, stack implements
- audit_trail            # Business requirement, stack provides
- soft_delete            # Business behavior, stack handles
- approval_workflow      # Business process, stack orchestrates

# ❌ BAD - Implementation details
- controller_service_repository  # Specific to layered architecture
- factory_pattern                # OOP design pattern
- django_class_based_view        # Framework-specific
- express_middleware_chain       # Framework-specific
- react_custom_hooks            # Technology-specific
```

### Layer 2: Stack Hints (Metadata)

**Purpose**: Guide stack generation without prescribing implementation.

**Mechanism**: Add metadata to entities that stacks interpret according to their idioms.

**Examples**:
```yaml
entity Order:
  # Domain vocabulary
  @use crud_operations()
  @use status_workflow(states=[Draft,Approved,Fulfilled])
  @use audit_trail()

  # Hints for stack (not prescriptive)
  hints:
    access_pattern: high_read      # Stack optimizes for reads
    consistency: strong            # Stack uses ACID transactions
    cache_strategy: write_through  # Stack implements caching
    search_fields: [title, customer]  # Stack builds indexes
```

**Stack Interpretations**:

| Hint | Django | Express | GraphQL | Serverless |
|------|--------|---------|---------|------------|
| high_read | select_related, cache | Redis cache | Dataloader | DynamoDB GSI |
| strong consistency | Transaction | Transaction | Transaction | DynamoDB strong |
| write_through | Signals | Middleware | Subscription | Stream trigger |
| search_fields | Postgres FTS | Elasticsearch | Algolia | CloudSearch |

### Layer 3: Stack-Specific Extensions (Opt-In)

**Purpose**: Allow teams with strong opinions to encode stack-specific patterns.

**Mechanism**: Separate vocabulary files per stack, loaded only when using that stack.

**Examples**:
```yaml
# dazzle/stack_vocab/django_patterns.yml
- id: django_rest_resource
  scope: django_api
  description: "Full Django REST resource with DRF best practices"
  expansion: |
    # Generates:
    # - Model with custom manager
    # - Serializer with validation
    # - ViewSet with mixins
    # - Admin with inline editing
    # - Tests with factory

# dazzle/stack_vocab/express_patterns.yml
- id: express_rest_resource
  scope: express_api
  description: "Express REST resource with CSR pattern"
  expansion: |
    # Generates:
    # - Routes with validation
    # - Controller (thin)
    # - Service (business logic)
    # - Repository (data access)
    # - Tests with supertest
```

## Cross-Stack Validity Test

Before adding a pattern to core vocabulary, evaluate across major stacks:

### Test Matrix

| Pattern | Django | Express | FastAPI | Next.js | GraphQL | Serverless | Include? |
|---------|--------|---------|---------|---------|---------|------------|----------|
| **Domain Operations** |
| CRUD operations | ✅ Admin | ✅ Routes | ✅ Routes | ✅ API | ✅ Mutations | ✅ Functions | **YES** |
| Search/filter | ✅ QuerySet | ✅ Query | ✅ Query | ✅ API | ✅ Args | ✅ Query | **YES** |
| Bulk operations | ✅ Bulk create | ✅ Array ops | ✅ Batch | ✅ API | ✅ Batch | ✅ Batch | **YES** |
| Export data | ✅ CSV | ✅ CSV | ✅ CSV | ✅ API | ✅ Query | ✅ S3 | **YES** |
| **State Management** |
| Status workflow | ✅ FSM | ✅ State | ✅ Enum | ✅ State | ✅ Enum | ✅ State | **YES** |
| Approval flow | ✅ Steps | ✅ Steps | ✅ Steps | ✅ Steps | ✅ Workflow | ✅ Step Fn | **YES** |
| Version control | ✅ Versions | ✅ Versions | ✅ Versions | ✅ History | ✅ History | ✅ Versions | **YES** |
| **Cross-Cutting** |
| Audit trail | ✅ Signals | ✅ Middleware | ✅ Depends | ✅ Middleware | ✅ Plugin | ✅ Stream | **YES** |
| Soft delete | ✅ Manager | ✅ Scope | ✅ Filter | ✅ Filter | ✅ Filter | ✅ Filter | **YES** |
| Multi-tenancy | ✅ Filter | ✅ Scope | ✅ Depends | ✅ Context | ✅ Context | ✅ Partition | **YES** |
| Rate limiting | ✅ Decorator | ✅ Middleware | ✅ Depends | ✅ Middleware | ✅ Plugin | ✅ API GW | **YES** |
| **Implementation Patterns** |
| CSR pattern | ✅ Yes | ✅ Yes | ✅ Yes | ⚠️ Awkward | ❌ No | ❌ No | **NO** |
| Factory pattern | ⚠️ Sometimes | ⚠️ Sometimes | ⚠️ Sometimes | ❌ Rare | ❌ No | ❌ No | **NO** |
| Observer pattern | ✅ Signals | ⚠️ Events | ⚠️ Events | ❌ Rare | ❌ No | ⚠️ Events | **NO** |
| Middleware chain | ⚠️ Limited | ✅ Core | ✅ Core | ⚠️ Different | ❌ No | ❌ No | **NO** |

**Legend**:
- ✅ Natural fit with framework idioms
- ⚠️ Possible but awkward or non-idiomatic
- ❌ Doesn't fit or is anti-pattern

## Design Patterns Analysis

### Gang of Four - Modern Relevance

| Pattern | Modern Use | Vocabulary Fit | Recommendation |
|---------|-----------|----------------|----------------|
| **Creational** |
| Factory | Moderate (DI, testing) | ❌ Implementation detail | Stack-specific only |
| Builder | Low (fluent APIs) | ❌ Implementation detail | Stack-specific only |
| Singleton | Low (anti-pattern) | ❌ Should not encode | Exclude |
| **Structural** |
| Adapter | Moderate (integrations) | ⚠️ Could abstract as "adapter" | Consider for integrations |
| Decorator | Moderate (middleware) | ❌ Stack-specific | Stack-specific only |
| Facade | High (service layer) | ⚠️ Could abstract as "service" | Consider with care |
| **Behavioral** |
| Observer | Moderate (events) | ⚠️ Could abstract as "events" | Consider with care |
| Strategy | Moderate (plugins) | ❌ Implementation detail | Stack-specific only |
| State | High (workflows) | ✅ Already have status_workflow | Include (abstracted) |

### Modern Patterns

| Pattern | Relevance | Vocabulary Fit | Recommendation |
|---------|-----------|----------------|----------------|
| Repository | High (data access) | ❌ Implementation | Stack decides |
| Service Layer | High (business logic) | ⚠️ Implied by operations | Implicit, not explicit |
| CQRS | Moderate (complex domains) | ⚠️ Could hint with read/write separation | Consider as hint |
| Event Sourcing | Low (specialized) | ❌ Too specific | Exclude from core |
| Saga | Low (distributed) | ❌ Too specific | Exclude from core |
| Circuit Breaker | Moderate (resilience) | ⚠️ Could be integration hint | Consider for integrations |

## Proposed Core Domain Patterns

### Operations Patterns

```yaml
- id: crud_operations
  kind: pattern
  scope: data
  description: "Full CRUD capabilities for entity"
  parameters:
    - name: entity_name
      type: string
      required: true
    - name: soft_delete
      type: boolean
      default: false
    - name: audit_trail
      type: boolean
      default: true
  hints:
    generates: [create, read, update, delete, list]
    permissions: [per_operation]
  # Stack interprets and generates appropriate code

- id: search_operations
  kind: pattern
  scope: data
  description: "Search and filtering capabilities"
  parameters:
    - name: search_fields
      type: list
      required: true
    - name: filter_fields
      type: list
      required: false
    - name: full_text
      type: boolean
      default: false
  hints:
    indexing: required
    query_optimization: true
```

### Workflow Patterns

```yaml
- id: status_workflow
  kind: pattern
  scope: workflow
  description: "State machine for entity lifecycle"
  parameters:
    - name: states
      type: list
      required: true
    - name: initial_state
      type: string
      required: true
    - name: final_states
      type: list
      required: false
  hints:
    validation: state_transitions
    audit: track_all_transitions
  # Stack generates FSM, validation, history

- id: approval_workflow
  kind: pattern
  scope: workflow
  description: "Multi-step approval process"
  parameters:
    - name: steps
      type: list
      required: true
    - name: approval_roles
      type: list
      required: true
  hints:
    notifications: on_state_change
    permissions: role_based
```

### Cross-Cutting Patterns

```yaml
- id: audit_trail
  kind: macro
  scope: data
  description: "Track all changes with who/when/what"
  hints:
    storage: append_only
    retention: configurable
  # Stack generates: created_by, updated_by, change_log

- id: soft_delete
  kind: macro
  scope: data
  description: "Mark as deleted without removing"
  hints:
    default_scope: exclude_deleted
    recovery: admin_only
  # Stack generates: deleted_at, deleted_by, is_deleted

- id: multi_tenant
  kind: macro
  scope: data
  description: "Isolate data by tenant/organization"
  parameters:
    - name: tenant_field
      type: string
      default: organization_id
  hints:
    isolation: row_level
    default_scope: current_tenant
```

## Implementation Strategy

### Phase 1: Foundation (Current)
- ✅ Basic vocabulary system (macro, alias, pattern)
- ✅ Template expansion with Jinja2
- ✅ CLI commands (list, show, expand)
- ✅ Example vocabularies (simple_task, support_tickets, urban_canopy)

### Phase 2: Domain Patterns (Next)
- [ ] Add domain operation patterns (CRUD, search, export)
- [ ] Add workflow patterns (status, approval, lifecycle)
- [ ] Add cross-cutting patterns (audit, soft-delete, multi-tenant)
- [ ] Test across multiple stacks (Django, Express, OpenAPI)
- [ ] Document pattern catalog

### Phase 3: Stack Hints (Future)
- [ ] Define hint vocabulary (access_pattern, consistency, caching)
- [ ] Update stacks to interpret hints
- [ ] Add hint validation
- [ ] Document hint interpretation per stack

### Phase 4: Stack Extensions (Future)
- [ ] Create stack-specific vocabulary files
- [ ] Add opt-in loading mechanism
- [ ] Create extension catalog
- [ ] Community contributions

## Examples in Practice

### Example 1: E-Commerce Order Entity

**Intent-Level DSL**:
```dsl
entity Order "Order":
  id: uuid pk
  customer: ref Customer required

  # Domain patterns
  @use crud_operations(soft_delete=true, audit_trail=true)
  @use status_workflow(
    states=[Draft, Submitted, Approved, Processing, Shipped, Delivered, Cancelled],
    initial_state=Draft,
    final_states=[Delivered, Cancelled]
  )
  @use search_operations(
    search_fields=[customer_name, order_number],
    filter_fields=[status, created_at],
    full_text=false
  )

  # Domain fields
  order_number: str(20) unique required
  total: decimal(10,2) required

  # Hints for stack
  hints:
    access_pattern: high_read
    consistency: strong
    cache_strategy: write_through
    search_indexing: elasticsearch
```

**Django Interprets As**:
```python
# Models
class Order(models.Model):
    # CRUD + soft_delete generates:
    deleted_at = models.DateTimeField(null=True)
    objects = OrderManager()  # Excludes deleted by default
    all_objects = models.Manager()

    # audit_trail generates:
    created_by = models.ForeignKey(User)
    updated_by = models.ForeignKey(User)

    # status_workflow generates:
    status = FSMField(default='Draft', choices=STATUS_CHOICES)

    @transition(source='Draft', target='Submitted')
    def submit(self):
        # Validation logic
        pass

    # Hints interpreted:
    class Meta:
        indexes = [
            models.Index(fields=['customer', 'created_at']),  # high_read
        ]

# Admin (from CRUD)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'customer', 'status', 'total']
    list_filter = ['status', 'created_at']
    search_fields = ['customer__name', 'order_number']
    readonly_fields = ['created_by', 'updated_by']  # audit_trail

# ViewSet (from CRUD)
class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    filter_backends = [SearchFilter, DjangoFilterBackend]
    search_fields = ['customer__name', 'order_number']
```

**Express Interprets As**:
```javascript
// Repository (from CRUD)
class OrderRepository {
  async create(data) { /* includes audit fields */ }
  async findById(id) { /* excludes soft-deleted */ }
  async update(id, data) { /* includes audit fields */ }
  async softDelete(id) { /* sets deleted_at */ }
  async search(query) { /* uses search_fields */ }
}

// Service (from status_workflow)
class OrderService {
  async submit(orderId) {
    // Validates transition Draft -> Submitted
    // Updates status, logs change (audit_trail)
  }

  async approve(orderId) {
    // Validates transition Submitted -> Approved
    // Sends notification (hint interpreted)
  }
}

// Routes (from CRUD + search)
router.get('/orders', searchMiddleware, orderController.list);
router.post('/orders', validateOrder, orderController.create);
router.put('/orders/:id/submit', orderController.submit);
```

### Example 2: Multi-Tenant SaaS Application

**Intent-Level DSL**:
```dsl
entity Project "Project":
  id: uuid pk

  # Multi-tenancy
  @use multi_tenant(tenant_field=organization_id)

  # Standard patterns
  @use crud_operations(audit_trail=true)
  @use status_workflow(
    states=[Active, Archived, Deleted],
    initial_state=Active
  )

  # Domain fields
  name: str(200) required
  description: text
  organization_id: ref Organization required

  hints:
    isolation: row_level
    default_scope: current_tenant
```

**Stack Interprets**:
- Django: Adds `organization_id` to default queryset filter
- Express: Adds middleware to scope all queries
- GraphQL: Adds context-based resolver filtering
- Serverless: Adds partition key for DynamoDB

## Benefits Summary

### Token Efficiency
- ✅ `@use crud_operations()` vs 50+ lines of DSL
- ✅ `@use status_workflow(...)` vs explicit state machine
- ✅ Clear intent in minimal tokens

### Constrained Ambiguity
- ✅ Pattern has clear meaning across stacks
- ✅ LLM knows what to generate for each stack
- ✅ Less variation in output

### Speed of Implementation
- ✅ LLM generates idiomatic code per stack
- ✅ No need to infer patterns from entity structure
- ✅ Best practices encoded

### Separation of Concerns
- ✅ Naturally emerges from stack interpretation
- ✅ Django gets Django best practices
- ✅ Express gets Express best practices

### Portability
- ✅ Same DSL works across Django, Express, GraphQL
- ✅ Can switch stacks without DSL changes
- ✅ Future-proof for new stacks

### Maintainability
- ✅ Intent stays stable even as implementations evolve
- ✅ Can update stack generation without touching DSL
- ✅ Pattern catalog grows over time

## Pitfalls to Avoid

### ❌ Don't Leak Implementation Details

**Bad**:
```yaml
- id: django_class_based_view_with_mixins
```

**Good**:
```yaml
- id: crud_operations  # Stack decides view type
```

### ❌ Don't Over-Specify

**Bad**:
```yaml
@use factory_pattern(builder=OrderBuilder, concrete=ConcreteOrder)
```

**Good**:
```yaml
@use crud_operations()  # Stack decides how to construct objects
```

### ❌ Don't Mix Abstraction Levels

**Bad**:
```yaml
entity Order:
  @use crud_operations()              # Domain level ✓
  @use controller_service_repository  # Implementation level ✗
```

**Good**:
```yaml
entity Order:
  @use crud_operations()    # Domain level
  @use status_workflow()    # Domain level
  @use audit_trail()        # Domain level
```

## Conclusion

The vocabulary system achieves its goals by staying at the **intent level**:
- Express WHAT the business needs (domain patterns)
- Provide HINTS about how it should behave (metadata)
- Let STACKS decide HOW to implement (idiomatic generation)

This keeps the DSL:
- **Portable** - Works across stacks
- **Efficient** - High token compression
- **Clear** - Unambiguous intent
- **Future-proof** - New stacks can implement patterns their way

Implementation patterns like CSR belong in **stack-specific extensions**, not core vocabulary.

## Next Steps

1. **Prototype domain patterns** - Implement 5-10 domain-level patterns
2. **Test across stacks** - Verify Django and Express can interpret idiomatically
3. **Document pattern catalog** - Create reference for pattern selection
4. **Gather feedback** - Validate with users building real apps
5. **Iterate** - Refine based on practical experience
