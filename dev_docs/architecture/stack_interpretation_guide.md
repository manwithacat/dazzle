# Stack Interpretation Guide - Domain Patterns

**Created**: 2025-11-23
**Status**: Implementation Guidance
**Purpose**: How stacks should interpret intent-level domain patterns

## Overview

Domain patterns express **business intent** (WHAT) without prescribing **implementation details** (HOW). Each stack interprets patterns according to its own idioms and best practices.

This document provides guidance for stack developers on how to interpret the domain patterns introduced in Phase 2.

## Pattern Interpretation Matrix

| Pattern | Django | Express | FastAPI | GraphQL | Next.js |
|---------|--------|---------|---------|---------|---------|
| soft_delete_behavior | Custom manager | Global scope | Query filter | Dataloader filter | API middleware |
| status_workflow_pattern | django-fsm | State machine lib | Pydantic + endpoints | Enum + validation | State + validation |
| searchable_entity | Postgres FTS / ES | Sequelize + ES | SQLAlchemy filters | Query args | Prisma filters |
| multi_tenant_isolation | Middleware + manager | Middleware + scope | Depends + filter | Context + loader | Session + filter |
| versioned_entity | django-simple-history | Versions table | History service | Version field | Audit table |

## Detailed Interpretations

### 1. soft_delete_behavior

**Intent**: Records are marked as deleted, not removed from database

**DSL Expansion**:
```dsl
entity Task:
  @use soft_delete_behavior(field_name=deleted_at, include_user=true)

# Expands to:
  deleted_at: datetime optional
  deleted_by: ref User
```

**Django Implementation**:
```python
# models.py
class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

class Task(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    objects = SoftDeleteManager()  # Default: exclude deleted
    all_objects = models.Manager()  # Include deleted

    def delete(self, *args, **kwargs):
        # Override to soft delete by default
        self.deleted_at = timezone.now()
        self.deleted_by = get_current_user()  # From middleware
        self.save()

    def hard_delete(self):
        # Actual deletion
        super().delete()

# admin.py
class TaskAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        # Show deleted items in admin with indicator
        return Task.all_objects.all()

    list_display = ['title', 'is_deleted']
    actions = ['restore_deleted']

    def is_deleted(self, obj):
        return obj.deleted_at is not None
    is_deleted.boolean = True
```

**Express Implementation**:
```javascript
// models/task.js
const Task = sequelize.define('Task', {
  deletedAt: {
    type: DataTypes.DATE,
    field: 'deleted_at'
  },
  deletedBy: {
    type: DataTypes.UUID,
    field: 'deleted_by'
  }
}, {
  defaultScope: {
    where: { deletedAt: null }  // Exclude deleted by default
  },
  scopes: {
    withDeleted: {
      where: {}  // Include deleted
    }
  }
});

// Soft delete method
Task.prototype.softDelete = async function(userId) {
  this.deletedAt = new Date();
  this.deletedBy = userId;
  await this.save();
};

// routes/tasks.js
router.delete('/tasks/:id', async (req, res) => {
  const task = await Task.findByPk(req.params.id);
  await task.softDelete(req.user.id);  // Soft delete
  res.json({ message: 'Task deleted' });
});

router.post('/tasks/:id/restore', async (req, res) => {
  const task = await Task.scope('withDeleted').findByPk(req.params.id);
  task.deletedAt = null;
  task.deletedBy = null;
  await task.save();
  res.json({ message: 'Task restored' });
});
```

**GraphQL Implementation**:
```graphql
# schema.graphql
type Task {
  id: ID!
  title: String!
  deletedAt: DateTime
  deletedBy: User
  isDeleted: Boolean!
}

type Query {
  tasks(includeDeleted: Boolean = false): [Task!]!
  task(id: ID!): Task
}

type Mutation {
  deleteTask(id: ID!): Task!
  restoreTask(id: ID!): Task!
}

# resolvers.js
const resolvers = {
  Query: {
    tasks: async (_, { includeDeleted }, { user }) => {
      const where = includeDeleted ? {} : { deleted_at: null };
      return await Task.findAll({ where });
    }
  },
  Mutation: {
    deleteTask: async (_, { id }, { user }) => {
      const task = await Task.findByPk(id);
      task.deleted_at = new Date();
      task.deleted_by = user.id;
      await task.save();
      return task;
    },
    restoreTask: async (_, { id }, { user }) => {
      const task = await Task.findByPk(id);
      task.deleted_at = null;
      task.deleted_by = null;
      await task.save();
      return task;
    }
  },
  Task: {
    isDeleted: (task) => task.deleted_at !== null
  }
};
```

---

### 2. status_workflow_pattern

**Intent**: State machine with valid transitions and tracking

**DSL Expansion**:
```dsl
entity Order:
  @use status_workflow_pattern(
    states=[draft, submitted, approved, processing, shipped],
    initial_state=draft,
    track_transitions=true
  )

# Expands to:
  status: enum[draft,submitted,approved,processing,shipped]=draft
  status_changed_at: datetime optional
  status_changed_by: ref User
```

**Django Implementation**:
```python
from django_fsm import FSMField, transition

class Order(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
    ]

    status = FSMField(default='draft', choices=STATUS_CHOICES)
    status_changed_at = models.DateTimeField(null=True)
    status_changed_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    @transition(field=status, source='draft', target='submitted')
    def submit(self, user):
        self.status_changed_at = timezone.now()
        self.status_changed_by = user
        # Optionally trigger notifications, webhooks, etc.

    @transition(field=status, source='submitted', target='approved')
    def approve(self, user):
        self.status_changed_at = timezone.now()
        self.status_changed_by = user

    @transition(field=status, source='approved', target='processing')
    def start_processing(self, user):
        self.status_changed_at = timezone.now()
        self.status_changed_by = user

# views.py
class OrderViewSet(viewsets.ModelViewSet):
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        order = self.get_object()
        try:
            order.submit(request.user)
            order.save()
            return Response({'status': 'submitted'})
        except TransitionNotAllowed:
            return Response({'error': 'Invalid transition'}, status=400)
```

**Express Implementation**:
```javascript
// models/order.js
const StateMachine = require('javascript-state-machine');

class Order extends Model {
  static init(sequelize) {
    return super.init({
      status: {
        type: DataTypes.ENUM('draft', 'submitted', 'approved', 'processing', 'shipped'),
        defaultValue: 'draft'
      },
      statusChangedAt: DataTypes.DATE,
      statusChangedBy: DataTypes.UUID
    }, { sequelize });
  }

  static initStateMachine(instance) {
    return new StateMachine({
      init: instance.status,
      transitions: [
        { name: 'submit', from: 'draft', to: 'submitted' },
        { name: 'approve', from: 'submitted', to: 'approved' },
        { name: 'startProcessing', from: 'approved', to: 'processing' },
        { name: 'ship', from: 'processing', to: 'shipped' }
      ],
      methods: {
        onAfterTransition: function(lifecycle) {
          instance.status = lifecycle.to;
          instance.statusChangedAt = new Date();
          // statusChangedBy set by caller
        }
      }
    });
  }
}

// services/orderService.js
class OrderService {
  async transitionStatus(orderId, transition, userId) {
    const order = await Order.findByPk(orderId);
    const fsm = Order.initStateMachine(order);

    if (!fsm.can(transition)) {
      throw new Error(`Invalid transition: ${transition}`);
    }

    fsm[transition]();
    order.statusChangedBy = userId;
    await order.save();

    // Emit event for notifications
    eventEmitter.emit('order.status_changed', { order, transition, userId });

    return order;
  }
}

// routes/orders.js
router.post('/orders/:id/submit', async (req, res) => {
  try {
    const order = await orderService.transitionStatus(
      req.params.id,
      'submit',
      req.user.id
    );
    res.json(order);
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});
```

---

### 3. multi_tenant_isolation

**Intent**: Isolate data by tenant/organization

**DSL Expansion**:
```dsl
entity Project:
  @use multi_tenant_isolation(tenant_field=organization_id)

# Expands to:
  organization_id: ref Organization required
```

**Django Implementation**:
```python
# middleware.py
class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Set current tenant from user's organization
            request.tenant = request.user.organization
            # Store in thread-local for use in managers
            _thread_locals.tenant = request.tenant
        return self.get_response(request)

# managers.py
class TenantManager(models.Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(_thread_locals, 'tenant') and _thread_locals.tenant:
            return qs.filter(organization=_thread_locals.tenant)
        return qs

# models.py
class Project(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)

    objects = TenantManager()  # Scoped to current tenant
    global_objects = models.Manager()  # Unscoped (admin only)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'created_at']),
        ]

    def save(self, *args, **kwargs):
        # Automatically set organization if not provided
        if not self.organization_id and hasattr(_thread_locals, 'tenant'):
            self.organization = _thread_locals.tenant
        super().save(*args, **kwargs)
```

**Express Implementation**:
```javascript
// middleware/tenant.js
function tenantMiddleware(req, res, next) {
  if (req.user) {
    req.tenant = req.user.organizationId;
  }
  next();
}

// models/project.js
const Project = sequelize.define('Project', {
  organizationId: {
    type: DataTypes.UUID,
    allowNull: false,
    field: 'organization_id'
  },
  name: DataTypes.STRING
}, {
  defaultScope: {
    // Will be overridden per-request
  },
  hooks: {
    beforeCreate: (project, options) => {
      // Auto-set tenant from context
      if (options.tenant && !project.organizationId) {
        project.organizationId = options.tenant;
      }
    }
  }
});

// Apply tenant scoping per-request
function applyTenantScope(req) {
  if (req.tenant) {
    return {
      where: { organizationId: req.tenant }
    };
  }
  return {};
}

// routes/projects.js
router.get('/projects', async (req, res) => {
  const projects = await Project.findAll(applyTenantScope(req));
  res.json(projects);
});

router.post('/projects', async (req, res) => {
  const project = await Project.create(req.body, {
    tenant: req.tenant
  });
  res.json(project);
});
```

---

## Implementation Checklist

When adding support for a domain pattern to a stack:

### For Stack Developers

- [ ] **Read pattern intent** - Understand business requirement
- [ ] **Choose idiomatic approach** - Use stack's best practices
- [ ] **Implement core behavior** - Ensure pattern works correctly
- [ ] **Add convenience methods** - Make pattern easy to use
- [ ] **Handle edge cases** - Null values, cascades, etc.
- [ ] **Add tests** - Verify pattern behavior
- [ ] **Document usage** - Examples for users
- [ ] **Consider performance** - Indexing, caching, etc.

### For Each Pattern

**soft_delete_behavior**:
- [ ] Default queries exclude deleted
- [ ] Admin/special queries can include deleted
- [ ] Provide restore functionality
- [ ] Handle cascading (should children be deleted too?)

**status_workflow_pattern**:
- [ ] Validate transitions
- [ ] Track who/when changed status
- [ ] Support transition hooks for notifications
- [ ] Provide endpoints/methods for each transition

**searchable_entity**:
- [ ] Create appropriate indexes
- [ ] Implement search endpoint/query
- [ ] Support filtering and sorting
- [ ] Handle pagination
- [ ] Consider full-text search if specified

**multi_tenant_isolation**:
- [ ] Automatically scope all queries to current tenant
- [ ] Prevent cross-tenant data access
- [ ] Auto-set tenant on create
- [ ] Include tenant in all indexes
- [ ] Provide admin bypass for super-users

**versioned_entity**:
- [ ] Store all versions
- [ ] Provide version history endpoint
- [ ] Support rollback to previous version
- [ ] Show current vs historical versions
- [ ] Handle storage efficiently

## Pattern Composition

Patterns often combine. Stacks should handle multiple patterns on same entity:

```dsl
entity Order:
  @use soft_delete_behavior()
  @use status_workflow_pattern(states=[...])
  @use multi_tenant_isolation()
  @use searchable_entity(search_fields=[...])
```

**Considerations**:
- Soft delete + tenant: Deleted items scoped to tenant
- Status workflow + versioning: Version on status change?
- Search + tenant: Search scoped to tenant
- All patterns + audit: Track everything

## Anti-Patterns to Avoid

### ❌ Don't Leak Implementation Details to DSL

**Bad**:
```python
# Don't add Django-specific fields to DSL expansion
fsm_state = FSMField(...)  # Too specific!
```

**Good**:
```python
# DSL just has intent, Django adds FSM internally
status = models.CharField(...)  # or FSMField, user doesn't know
```

### ❌ Don't Ignore Stack Idioms

**Bad**:
```javascript
// Implementing Django patterns in Express
class OrderManager extends BaseManager { ... }  // Not idiomatic
```

**Good**:
```javascript
// Use Express/Sequelize idioms
Order.addScope('defaultScope', { where: { ... } });
```

### ❌ Don't Over-Generate

**Bad**:
```python
# Generating 100 lines for simple pattern
# ... massive boilerplate ...
```

**Good**:
```python
# Concise, idiomatic implementation
# Leverage framework features
```

## Next Steps

1. **Implement in Django stack** - Start with 2-3 patterns
2. **Implement in Express stack** - Same 2-3 patterns
3. **Compare implementations** - Ensure intent preserved
4. **Document differences** - Why stacks differ
5. **Test cross-stack** - Same DSL, both stacks
6. **Iterate** - Refine based on experience

## Conclusion

Domain patterns express **intent**, stacks provide **implementation**. This separation:
- Keeps DSL portable
- Allows stack-specific optimization
- Enables best practices per stack
- Future-proofs against new stacks

Each stack should interpret patterns according to its own idioms, not try to mimic other stacks.
