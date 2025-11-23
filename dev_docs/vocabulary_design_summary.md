# Vocabulary Design - Summary

**Created**: 2025-11-23
**Status**: Documented and Proposed

## What Was Done

### 1. Design Philosophy Document
**File**: `dev_docs/architecture/vocabulary_design_philosophy.md` (400+ lines)

**Key Decisions**:
- ✅ Vocabulary should express **intent** (WHAT), not **implementation** (HOW)
- ✅ Use **three-layer model**: Core domain vocabulary, Stack hints, Stack extensions
- ✅ Apply **cross-stack validity test** before adding patterns to core
- ✅ Keep domain patterns **portable** across Django, Express, FastAPI, Next.js, GraphQL, Serverless

**Core Principle**:
```
Can this pattern be implemented idiomatically across all major stacks?
  ✅ YES → Include in core vocabulary
  ⚠️ PARTIALLY → Abstract it or use hints
  ❌ NO → Move to stack-specific extensions
```

**What Belongs in Core Vocabulary**:
- Domain operations (CRUD, search, export)
- Business workflows (status, approval, scheduling)
- Cross-cutting concerns (audit, soft-delete, multi-tenancy)
- Integration patterns (webhooks, events)

**What Does NOT Belong**:
- Implementation patterns (Controller-Service-Repository, Factory, Observer)
- Framework specifics (Django forms, Express middleware)
- Architecture decisions (monolith vs microservices)
- Technology choices (REST vs GraphQL)

### 2. Domain Patterns Catalog
**File**: `dev_docs/architecture/domain_patterns_catalog.md` (500+ lines)

**Cataloged 15 Intent-Level Patterns**:

**Operations** (3 patterns):
1. `crud_operations` - Full CRUD capabilities
2. `search_operations` - Search, filter, sort
3. `export_operations` - Export to CSV/JSON/Excel

**Workflows** (3 patterns):
4. `status_workflow` - State machine with transitions
5. `approval_workflow` - Multi-step approval process
6. `scheduled_workflow` - Time-based automation

**Cross-Cutting** (5 patterns):
7. `audit_trail` - Track all changes (who/when/what)
8. `soft_delete` - Mark as deleted without removing
9. `multi_tenant` - Data isolation by organization
10. `rate_limiting` - Prevent abuse/overuse
11. `version_control` - Track entity versions

**Integration** (4 patterns):
12. `webhook_integration` - HTTP callbacks on events
13. `event_sourcing` - Append-only event log
14. `cache_strategy` - Caching behavior hints
15. `search_indexing` - Full-text search integration

**Each Pattern Includes**:
- Intent description
- Use cases
- Parameters
- Hints for stack interpretation
- Stack-specific implementations (Django, Express, FastAPI, etc.)
- Usage examples

### 3. Practical Examples

**E-Commerce Order** (Complex composition):
```dsl
entity Order:
  @use crud_operations(soft_delete=true, audit_trail=true)
  @use search_operations(search_fields=[order_number, customer])
  @use export_operations(formats=[csv, excel])
  @use status_workflow(
    states=[Draft, Submitted, Approved, Processing, Shipped, Delivered],
    initial_state=Draft
  )
  @use multi_tenant(tenant_field=merchant_id)
  @use rate_limiting(operations=[create], rate="10 per minute")
  @use webhook_integration(events=[status_changed, delivered])
```

**SaaS Project** (Multi-tenant):
```dsl
entity Project:
  @use multi_tenant(tenant_field=organization_id)
  @use crud_operations(soft_delete=true, audit_trail=true)
  @use status_workflow(states=[Active, Archived, Deleted])
  @use rate_limiting(operations=[create], rate="100 per day", scope=organization)
```

**Content Management** (Approval workflow):
```dsl
entity Article:
  @use crud_operations(audit_trail=true)
  @use search_operations(search_fields=[title, content], full_text=true)
  @use status_workflow(states=[Draft, InReview, Published, Archived])
  @use approval_workflow(
    steps=[EditorReview, LegalReview],
    approver_roles=[Editor, Legal]
  )
  @use scheduled_workflow(
    schedule_type=cron,
    schedule_spec="0 0 * * *",
    action=archive_old_drafts
  )
```

## Key Insights

### Why This Approach Works

**1. Token Efficiency**
- `@use crud_operations()` compresses 50+ lines of DSL
- Clear intent in minimal tokens
- LLM understands pattern immediately

**2. Constrained Ambiguity**
- Pattern has ONE clear meaning
- Stack knows exactly what to generate
- Less variation in LLM output

**3. Portability**
- Same DSL works across Django, Express, GraphQL
- Can switch stacks without changing DSL
- Future-proof for new frameworks

**4. Separation of Concerns**
- Django generates Django best practices
- Express generates Express best practices
- Each stack implements idiomatically

**5. Composability**
- Patterns combine naturally
- Rich behavior from simple declarations
- No conflicts or overlaps

### Gang of Four Patterns - Analysis

**Evaluated for inclusion**:
| Pattern | Modern Use | Verdict | Reason |
|---------|-----------|---------|---------|
| Factory | Moderate | ❌ Exclude | Implementation detail, stack decides |
| Singleton | Low | ❌ Exclude | Anti-pattern in modern systems |
| Observer | Moderate | ⚠️ Abstract | Include as "event_handling" |
| Strategy | Moderate | ❌ Exclude | Implementation detail |
| State | High | ✅ Include | As "status_workflow" (abstracted) |

**Conclusion**: Classic patterns are too implementation-specific. Abstract to business intent instead.

### Modern Patterns - Analysis

| Pattern | Relevance | Verdict | Reason |
|---------|-----------|---------|---------|
| Repository | High | ❌ Exclude | Stack decides data access layer |
| Service Layer | High | ⚠️ Implicit | Implied by operations, not explicit |
| CQRS | Moderate | ⚠️ Consider | Could be hint for read/write separation |
| Event Sourcing | Low | ❌ Exclude | Too specialized |
| Circuit Breaker | Moderate | ⚠️ Consider | For integration patterns |

**Conclusion**: Include high-level concepts (CQRS as hint), exclude specific implementations.

## Benefits Summary

### For Users
- ✅ **Write less DSL** - Patterns compress common requirements
- ✅ **Clear intent** - Explicit about business needs
- ✅ **Best practices** - Patterns encode proven approaches
- ✅ **Consistent** - Same patterns across projects

### For LLMs
- ✅ **Faster generation** - Knows what to generate immediately
- ✅ **Better quality** - Follows stack best practices
- ✅ **Less ambiguity** - Pattern has clear meaning
- ✅ **Idiomatic code** - Generates natural code per stack

### For DAZZLE
- ✅ **Portable** - DSL works across stacks
- ✅ **Maintainable** - Intent stable, implementations evolve
- ✅ **Extensible** - Easy to add new patterns
- ✅ **Future-proof** - New stacks implement patterns their way

## What This Avoids

### ❌ Excessive Purity
```dsl
# Too abstract, no guidance
entity Task:
  title: string
  # LLM has to guess everything
```

### ❌ Excessive Specificity
```dsl
# Too prescriptive, not portable
entity Task:
  @use django_class_based_view_with_permission_mixins()
  @use controller_service_repository_with_dependency_injection()
  # Locked into specific stack and pattern
```

### ✅ Right Balance
```dsl
# Clear intent, stack decides implementation
entity Task:
  @use crud_operations()              # WHAT: needs CRUD
  @use status_workflow(...)           # WHAT: state machine
  @use audit_trail()                  # WHAT: track changes

  # Hints (not prescriptive)
  hints:
    access_pattern: high_read         # Stack optimizes
    consistency: strong               # Stack ensures ACID
```

## Implementation Strategy

### Phase 2A: Prototype (Immediate)
- [ ] Implement 3-5 domain patterns in one example vocabulary
- [ ] Test with Django stack generation
- [ ] Test with Express stack generation
- [ ] Validate cross-stack portability

**Suggested First Patterns**:
1. `crud_operations` - Most common, high value
2. `status_workflow` - Clear business value
3. `audit_trail` - Cross-cutting, well-understood

### Phase 2B: Expand (Near-term)
- [ ] Add 5-10 more patterns based on feedback
- [ ] Test with additional stacks (FastAPI, GraphQL)
- [ ] Document stack interpretation guides
- [ ] Gather user feedback

### Phase 3: Stack Hints (Future)
- [ ] Define hint vocabulary
- [ ] Update stacks to interpret hints
- [ ] Add validation for hints
- [ ] Document hint semantics

### Phase 4: Stack Extensions (Future)
- [ ] Create stack-specific vocabularies
- [ ] Build opt-in loading mechanism
- [ ] Enable community contributions
- [ ] Create extension marketplace

## Files Created

1. **`vocabulary_design_philosophy.md`** (9,500 words)
   - Three-layer model
   - Cross-stack validity test
   - Pattern analysis (GoF, modern patterns)
   - Examples and anti-patterns

2. **`domain_patterns_catalog.md`** (6,000 words)
   - 15 intent-level patterns
   - Parameters and hints for each
   - Stack interpretations
   - Usage examples

3. **`vocabulary_design_summary.md`** (This file)
   - Executive summary
   - Key decisions and insights
   - Implementation roadmap

**Total**: 15,500+ words of design documentation

## Next Actions

### Immediate (User Decision)
1. **Review design philosophy** - Approve approach?
2. **Select starter patterns** - Which 3-5 to prototype?
3. **Choose test stacks** - Django + Express to start?

### Short-term (If Approved)
1. **Implement patterns** - Add to example vocabulary
2. **Update stacks** - Teach Django/Express to interpret patterns
3. **Test end-to-end** - DSL → pattern → generated code
4. **Document** - How to use patterns, how stacks interpret

### Long-term (Future Phases)
1. **Expand catalog** - More patterns based on usage
2. **Add hints system** - Stack optimization hints
3. **Stack extensions** - Optional pattern libraries
4. **Community** - Allow contributions

## Questions for Consideration

1. **Pattern Selection**: Which 3-5 patterns should we prototype first?
2. **Stack Priority**: Start with Django + Express, or also include FastAPI/GraphQL?
3. **Implementation Depth**: Should stacks fully implement patterns, or start with basic support?
4. **Migration Path**: How do existing examples adopt these patterns?
5. **Documentation**: Should we create user-facing pattern guide now or after prototype?

## Conclusion

The design documentation provides a **clear framework** for vocabulary evolution:
- **What to include** - Intent-level domain patterns
- **What to exclude** - Implementation-specific patterns
- **How to validate** - Cross-stack validity test
- **How to implement** - Three-layer model with hints

This approach achieves the original goals:
- ✅ Token efficiency (high compression ratios)
- ✅ Constrained ambiguity (clear intent)
- ✅ Speed of implementation (LLM knows what to generate)
- ✅ Separation of concerns (emerges naturally from stack idioms)

The boundary between purity and specificity is now **clearly defined** and **testable**.

**Ready for prototype implementation when approved.**
