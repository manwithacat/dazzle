# Design Pattern DSL (DP-DSL) - Evaluation and Implementation Roadmap

**Date**: 2025-11-23
**Status**: Planned for v0.3.0+
**Evaluator**: Claude Code
**Source Proposal**: `dazzle_second_bottleneck_dp_dsl_practical_recs_v1.md`

---

## Executive Summary

The DP-DSL proposal introduces a **second evolutionary bottleneck** between Domain DSL and Core Implementation DSL to explicitly model architectural design patterns.

**Verdict**: Architecturally sound but **premature for v0.2.0**. Recommend phased implementation starting v0.3.0+.

**Key Finding**: The vision is excellent for long-term DAZZLE evolution, but requires careful phasing to avoid destabilizing the ecosystem and overwhelming users.

---

## Proposal Overview

### Concept
Add an intermediate layer between Domain DSL (business concepts) and Core DSL (implementation details):

```
Domain DSL (business concepts)
    ↓
DP-DSL (design patterns) ← NEW LAYER
    ↓
Core Implementation DSL (current .dsl files)
    ↓
Generated Code (Django, Express, etc.)
```

### Key Features
- **Pattern Vocabulary**: Explicit modeling of factory, strategy, adapter, ports-and-adapters, CQRS, repository, saga, etc.
- **Stack-Neutral**: Patterns described in framework-agnostic terms
- **Deterministic Expansion**: DP-DSL always compiles to Core DSL
- **Token-Efficient**: Maintains LLM-friendliness
- **Validation**: Structural checks before code generation
- **Metadata**: Tags, complexity, change_risk for pattern mining

### Proposed File Structure
```
dazzle/
  domain/
    app_domain.dsl.yml          # Business concepts
  design/
    app_patterns.dp.yml         # Design patterns (NEW)
    domain_mapping.yml          # Cross-layer mapping (NEW)
    DESIGN_PATTERNS.md          # Human docs (NEW)
  build/
    app_core_dsl.yml            # Expanded core DSL
    dp_validation_errors.json   # Validation output
```

---

## Evaluation

### Strengths ⭐⭐⭐⭐⭐

1. **Addresses Real Gap**
   - DAZZLE currently has no explicit pattern modeling
   - Patterns emerge implicitly from stack-specific generation
   - No way to evolve patterns independently of stacks

2. **Clean Architectural Separation**
   - Domain DSL: Business problem space
   - DP-DSL: Architectural solution space
   - Core DSL: Implementation details
   - Proper separation of concerns

3. **Stack Independence**
   - Patterns use neutral terms (port, adapter, domain_model)
   - Not coupled to Django, Express, FastAPI, etc.
   - Same patterns can drive multiple backends

4. **Token Efficiency**
   - YAML format with short keys
   - Explicit references vs prose
   - LLM-friendly structure maintained

5. **Validation & Safety**
   - Pre-expansion validation catches errors early
   - Machine-readable error outputs
   - Referential integrity checks

6. **Evolvability**
   - Patterns can evolve without breaking apps
   - Metadata enables pattern mining and discovery
   - Clear migration paths between pattern versions

### Critical Concerns 🔴

#### 1. **Timing & Maturity** ⚠️
- DAZZLE v0.1.1 just stabilized with single-layer DSL
- Users still learning current model
- v0.2.0 should focus on production readiness (tests, migrations)
- Adding second DSL layer too early risks fragmentation

**Impact**: High cognitive load for users, delays critical features

#### 2. **Implementation Scope** 🔴
Requires extensive work across entire system:
- New DP-DSL parser (YAML format)
- Pattern expansion engine
- Validation system with referential integrity
- Updates to ALL 6 stacks to consume pattern-shaped core DSL
- Domain mapping system
- Migration tools for existing apps
- LSP server updates for DP-DSL files
- Comprehensive documentation
- Testing infrastructure

**Estimate**: 3-4 months full-time development

#### 3. **Pattern Selection Problem** 🔴
Proposal suggests heuristics:
- "If use case touches ≥2 external systems → ports_and_adapters"
- "If business logic has ≥2 algorithms → strategy"

**Problem**: Real pattern selection requires:
- Deep domain understanding
- Non-functional requirements analysis
- Team capabilities assessment
- Evolution timeline planning

Simple heuristics produce poor architectures. Sophisticated LLM-based inference needed, adding uncertainty.

#### 4. **Core DSL Expansion Semantics Undefined** ⚠️
Proposal says DP-DSL "deterministically expands to core DSL" but doesn't show how.

**Example**:
```yaml
# DP-DSL Input
patterns:
  - id: "user_registration_flow"
    kind: "ports_and_adapters"
    ports:
      - name: "user_repository"
        role: "outbound"
```

**Core DSL Output**: ???
- How do ports map to existing `service`, `integration`, `entity` constructs?
- What new core DSL blocks are needed?
- How do stacks interpret pattern-shaped core DSL?

**Needs**: Complete expansion semantics definition with examples

#### 5. **User Experience & Authorship** ⚠️
Who creates the DP-DSL?

**Option A - Manual Authoring**:
- Developers write `app_patterns.dp.yml` by hand
- Requires architectural expertise
- High barrier to entry for new users

**Option B - LLM-Generated**:
- Agent infers patterns from Domain DSL
- Requires confidence in pattern selection quality
- Unclear how users override incorrect choices

**Option C - Hybrid** (Best but complex):
- LLM suggests patterns
- User reviews and edits
- Needs sophisticated tooling (diffs, explanations, alternatives)

**Proposal doesn't specify** - critical UX gap

#### 6. **Backwards Compatibility** 🔴
No strategy for existing apps:
- Can simple_task run without DP-DSL?
- Migration path for urban_canopy?
- Do stacks support both DP-DSL and non-DP-DSL modes?
- How long must dual-mode support last?

**Needs**: Explicit backwards compatibility and migration strategy

#### 7. **Stack Update Burden** ⚠️
Each of 6 stacks needs significant refactoring:

**Example - Express Micro Stack**:
Currently: Generates routes directly from `surface` blocks

With ports-and-adapters needs to generate:
- Port interfaces (TypeScript interfaces)
- Adapter implementations
- Application service layer
- Dependency injection container
- Transaction boundary enforcement

**Estimate**: 2-4 weeks per stack × 6 stacks = 3-6 months

#### 8. **Tooling & Developer Experience** ⚠️
Requires new tooling:
- LSP server support for DP-DSL files
- Syntax highlighting in VS Code extension
- Validation and error reporting across layers
- Go-to-definition across Domain → DP → Core
- Debugging story when generated code fails
- Documentation generation from DP-DSL

**Current state**: None of this exists

---

## Alternative Approaches

### Option 1: Pattern Annotations (Recommended for v0.3.0)

Add annotations to current DSL instead of separate file:

```dsl
experience RegisterUser {
  @pattern ports_and_adapters
  @port user_repository outbound UserRepository
  @port email_service outbound EmailNotifier

  step validate_email
  step create_account
  step send_welcome
}
```

**Pros**:
- Single DSL to learn
- Gradual adoption (annotations optional)
- Stacks can ignore unsupported annotations
- Lower implementation cost
- Backwards compatible by default

**Cons**:
- Mixes concerns (domain + patterns)
- Less explicit than separate DP-DSL file
- May clutter domain specifications

**Recommendation**: Start here for v0.3.0

### Option 2: Stack-Level Pattern Flags

Apply patterns at build time:
```bash
dazzle build --stack django_micro --patterns ports-and-adapters,repository
```

**Pros**:
- Zero DSL changes
- Immediate implementation possible
- Easy to experiment

**Cons**:
- Not captured in project files
- Can't vary patterns per use case
- Less explicit and discoverable

**Recommendation**: Good for prototyping, not production

### Option 3: Pattern Templates

Generate pattern boilerplate on demand:
```bash
dazzle pattern apply ports-and-adapters to RegisterUser
```

Creates core DSL fragments following pattern.

**Pros**:
- Explicit pattern modeling
- Works with current DSL
- User has full control

**Cons**:
- Manual process
- No automatic pattern inference
- Potential for inconsistency

**Recommendation**: Useful tool but doesn't replace full DP-DSL

---

## Phased Implementation Roadmap

### Phase 1: v0.3.0 - Pattern Annotations (Q1 2026)

**Goal**: Introduce pattern support without architectural complexity

**Implementation**:
1. Add `@pattern` annotation syntax to DSL parser
2. Implement in 2 stacks: django_micro_modular, express_micro
3. Support 5 core patterns:
   - `repository` - data access abstraction
   - `service` - application service/use case
   - `ports_and_adapters` - hexagonal architecture
   - `cqrs` - basic read/write separation
   - `observer` - event handling

4. Make annotations **optional** - apps work without them
5. Generate pattern-appropriate code structure
6. Document patterns in stack capabilities matrix
7. Gather usage data and user feedback

**Success Criteria**:
- At least 3 real apps using pattern annotations
- User feedback validates usefulness
- Stack generation quality improves
- No increase in error rates

**Effort**: 3-4 weeks development + 2 weeks documentation

**Deliverables**:
- Pattern annotation syntax in DSL reference
- Pattern-aware code generation in 2 stacks
- Pattern usage guide
- Examples demonstrating each pattern

### Phase 2: v0.4.0 - DP-DSL Prototype (Q2 2026)

**Goal**: Validate separate DP-DSL layer with proven patterns

**Prerequisites**:
- v0.3.0 pattern annotations in production use
- User feedback validates pattern value
- Clear data on which patterns matter most

**Implementation**:
1. Design DP-DSL schema (YAML) for proven patterns only
2. Implement DP-DSL parser and validator
3. Create pattern expansion engine (DP-DSL → Core DSL)
4. Support **dual mode**:
   - Apps can use annotations OR DP-DSL
   - Not both (avoid confusion)
5. Create migration tool: annotations → DP-DSL
6. Implement in same 2 stacks from v0.3.0
7. Test with 2-3 real apps (simple_task, urban_canopy, support_tickets)
8. Document expansion semantics with examples

**Success Criteria**:
- DP-DSL correctly expands to core DSL
- Generated code quality matches annotation approach
- Users understand dual-mode model
- Migration tool works reliably
- LSP server provides basic DP-DSL support

**Effort**: 6-8 weeks development + 3 weeks documentation

**Deliverables**:
- DP-DSL specification and schema
- Pattern expansion examples
- Migration tool (annotations → DP-DSL)
- Updated stack documentation
- Basic LSP support for DP-DSL files

### Phase 3: v0.5.0 - Full DP-DSL (Q3 2026)

**Goal**: Production-ready DP-DSL with full pattern vocabulary

**Prerequisites**:
- v0.4.0 DP-DSL prototype validated
- Architecture proven with real apps
- User adoption shows value

**Implementation**:
1. Complete pattern vocabulary:
   - factory, abstract_factory
   - strategy, template_method
   - adapter, facade, bridge
   - observer, pubsub, mediator
   - saga, process_manager
   - decorator, proxy
   - command, event_sourcing

2. LLM-based pattern inference:
   - Analyze Domain DSL
   - Suggest appropriate patterns
   - Explain reasoning
   - User reviews and approves

3. Rich validation:
   - Architectural linting
   - Pattern consistency checks
   - Anti-pattern detection
   - Performance implications

4. Full stack support:
   - All 6 current stacks
   - Pattern compatibility matrix
   - Graceful degradation for unsupported patterns

5. Advanced tooling:
   - Full LSP integration
   - Pattern refactoring tools
   - Cross-layer navigation
   - Debugging support

6. Migration tools:
   - Automatic legacy app migration
   - Pattern suggestion for existing apps
   - Validation and testing

**Success Criteria**:
- 10+ patterns supported
- All 6 stacks handle patterns correctly
- LLM pattern inference accuracy >80%
- User satisfaction >4/5
- No regressions in existing apps

**Effort**: 8-12 weeks development + 4 weeks documentation

**Deliverables**:
- Complete DP-DSL specification
- Full pattern catalog with examples
- LLM pattern inference system
- Migration tools and guides
- Comprehensive documentation
- Pattern library and templates

---

## Key Questions to Answer Before Phase 1

### 1. Market Validation
**Question**: Do DAZZLE users actually need explicit pattern modeling?

**Method**:
- Survey early adopters
- Interview users building complex apps
- Analyze support requests for pattern-related issues

**Success**: >60% of users express need for pattern support

### 2. Pattern Priorities
**Question**: Which 3-5 patterns deliver 80% of value?

**Method**:
- Analyze existing generated apps
- Survey architectural patterns in real projects
- Review Django/Express/FastAPI best practices

**Expected**: repository, service, ports_and_adapters, cqrs, observer

### 3. Complete Example
**Question**: How does full flow work end-to-end?

**Required**: Show for UserRegistration with ports-and-adapters:
1. Domain DSL specification
2. DP-DSL pattern declaration
3. Core DSL expansion
4. Generated Django code
5. Generated Express code

**Deliverable**: Working example project demonstrating full flow

### 4. LSP Integration
**Question**: How does tooling support multi-layer DSL?

**Required**:
- DP-DSL syntax highlighting
- Cross-layer go-to-definition
- Validation errors across layers
- Hover documentation for patterns

**Deliverable**: VS Code extension prototype with DP-DSL support

### 5. Debugging Story
**Question**: When generated code fails, how do users trace back?

**Scenario**:
- Runtime error in Django view
- Error originated from ports-and-adapters pattern
- User needs to understand: Code → Core DSL → DP-DSL → Domain DSL

**Required**:
- Source mapping across layers
- Error contextualization
- Pattern documentation links

**Deliverable**: Debugging guide with examples

### 6. Stack Compatibility Matrix
**Question**: Which stacks support which patterns?

**Required Matrix**:
```
               repository  service  ports_and_adapters  cqrs  observer
django_micro        ✓         ✓            ✓             ✓       ✓
express_micro       ✓         ✓            ✓             -       ✓
django_api          ✓         ✓            ✓             ✓       ✓
openapi             -         -            -             -       -
docker              -         -            -             -       -
terraform           -         -            -             -       -
```

**Deliverable**: Compatibility matrix in documentation

---

## Design Spike Recommendation

**Before committing to Phase 1**, create a **design spike**:

### Spike Goal
Validate the DP-DSL concept with minimal implementation

### Spike Scope
Implement **one pattern** (ports-and-adapters) for **one use case** (UserRegistration) in **one stack** (django_micro_modular).

### Spike Deliverables

1. **Domain DSL** - `examples/pattern_spike/dsl/domain.dsl`
   ```dsl
   app PatternSpike {
     title: "Pattern DP-DSL Spike"
   }

   entity User {
     field email String(200) required unique
     field name String(100) required
   }

   experience RegisterUser {
     step validate_email
     step create_account
     step send_welcome
   }
   ```

2. **DP-DSL** - `examples/pattern_spike/design/patterns.dp.yml`
   ```yaml
   patterns:
     - id: "user_registration_flow"
       kind: "ports_and_adapters"
       applies_to:
         domain_use_case: "RegisterUser"
       ports:
         - name: "user_repository"
           role: "outbound"
           contract: "UserRepository"
         - name: "email_service"
           role: "outbound"
           contract: "EmailNotifier"
       policies:
         transaction_boundary: "use_case"
         validation_strategy: "domain"
   ```

3. **Core DSL** - `examples/pattern_spike/build/core.dsl` (expanded)
   ```dsl
   # Expanded from DP-DSL
   service UserRegistrationService {
     operation register(email, name) {
       port user_repository
       port email_service

       step validate_email
       step create_account
       step send_welcome
     }
   }

   integration UserRepository {
     contract: "UserRepository"
     operations: [save, find_by_email]
   }

   integration EmailNotifier {
     contract: "EmailNotifier"
     operations: [send_welcome_email]
   }
   ```

4. **Generated Django Code**:
   - `domain/user.py` - Domain model
   - `application/user_registration_service.py` - Application service
   - `ports/user_repository.py` - Repository interface
   - `ports/email_notifier.py` - Email service interface
   - `adapters/django_user_repository.py` - Django ORM adapter
   - `adapters/smtp_email_notifier.py` - SMTP adapter
   - `views.py` - HTTP adapter calling service

5. **Documentation**:
   - Expansion semantics: DP-DSL → Core DSL
   - Code generation: Core DSL → Django
   - Developer guide for using the pattern

### Spike Success Criteria
- DP-DSL cleanly expands to Core DSL
- Generated code follows ports-and-adapters correctly
- Clear separation: domain, application, ports, adapters
- Code is testable (can mock ports)
- Expansion is deterministic and documented

### Spike Timeline
- **Week 1**: Design DP-DSL schema and expansion rules
- **Week 2**: Implement expansion engine prototype
- **Week 3**: Update django_micro stack for pattern support
- **Week 4**: Test, document, demo

**If spike succeeds**: Proceed with Phase 1
**If spike struggles**: Revise approach or defer to later version

---

## Risk Assessment

### High Risks 🔴

1. **Complexity Creep**
   - **Risk**: DP-DSL adds too much conceptual overhead
   - **Mitigation**: Start with 3-5 patterns max, gather feedback
   - **Indicator**: User confusion, low adoption

2. **Poor Pattern Selection**
   - **Risk**: Automated pattern inference produces bad architectures
   - **Mitigation**: Human-in-loop review, clear explanations
   - **Indicator**: Users override suggestions frequently

3. **Stack Fragmentation**
   - **Risk**: Some stacks support patterns, others don't
   - **Mitigation**: Clear compatibility matrix, graceful degradation
   - **Indicator**: User complaints about stack limitations

### Medium Risks ⚠️

4. **Implementation Delay**
   - **Risk**: DP-DSL delays critical v0.2.0 features
   - **Mitigation**: Defer to v0.3.0+, strict phasing
   - **Indicator**: Roadmap slippage

5. **Migration Burden**
   - **Risk**: Existing apps hard to migrate
   - **Mitigation**: Excellent migration tools, dual-mode support
   - **Indicator**: Users stick with old version

6. **Validation Complexity**
   - **Risk**: Pattern validation catches too few or too many errors
   - **Mitigation**: Iterative refinement with real apps
   - **Indicator**: False positives/negatives

### Low Risks ✓

7. **Token Efficiency**
   - **Risk**: DP-DSL too verbose for LLMs
   - **Mitigation**: YAML format is already compact
   - **Indicator**: LLM context overflow

8. **Documentation Debt**
   - **Risk**: Insufficient pattern documentation
   - **Mitigation**: Document patterns as they're added
   - **Indicator**: Support questions about patterns

---

## Success Metrics

### v0.3.0 (Pattern Annotations)
- ✅ ≥3 real apps using annotations
- ✅ User satisfaction ≥3.5/5
- ✅ Pattern-generated code passes tests
- ✅ No increase in error rates vs v0.2.0

### v0.4.0 (DP-DSL Prototype)
- ✅ DP-DSL → Core DSL expansion works correctly
- ✅ ≥2 apps migrated from annotations to DP-DSL
- ✅ Migration tool success rate ≥95%
- ✅ LSP provides basic DP-DSL support

### v0.5.0 (Full DP-DSL)
- ✅ ≥10 patterns supported and documented
- ✅ All 6 stacks handle core patterns
- ✅ LLM pattern inference accuracy ≥80%
- ✅ User adoption ≥40% of complex apps
- ✅ No regressions in existing functionality

---

## Recommendation Summary

| Aspect | Rating | Recommendation |
|--------|--------|----------------|
| **Architectural Vision** | ⭐⭐⭐⭐⭐ | Excellent long-term direction |
| **Current Timing** | ⭐⭐ | Too early for v0.2.0 |
| **Implementation Scope** | ⭐⭐ | Needs careful phasing |
| **User Value** | ⭐⭐⭐⭐ | High for complex apps |
| **Risk Level** | ⭐⭐ | Medium-high if rushed |
| **Backwards Compat** | ⭐⭐⭐ | Requires explicit strategy |

### Immediate Actions

1. **For v0.2.0** (Current): ❌ **Do NOT implement DP-DSL**
   - Focus on production readiness: tests, migrations, health checks
   - These deliver immediate user value with lower risk

2. **For v0.3.0** (Next): ✅ **Implement Pattern Annotations**
   - Add @pattern annotations to current DSL
   - Support 5 core patterns in 2 stacks
   - Gather usage data and feedback
   - Validate the pattern approach

3. **Before v0.4.0**: ✅ **Run Design Spike**
   - Implement ports-and-adapters for UserRegistration
   - Validate DP-DSL expansion semantics
   - Document complete example flow
   - Prove the architecture works

4. **For v0.4.0** (If spike succeeds): ✅ **DP-DSL Prototype**
   - Separate DP-DSL file support
   - Dual-mode: annotations OR DP-DSL
   - Migration tooling
   - Full expansion documentation

5. **For v0.5.0** (If prototype proves valuable): ✅ **Full DP-DSL**
   - Complete pattern vocabulary
   - LLM pattern inference
   - All stack support
   - Production-ready tooling

---

## Conclusion

The Design Pattern DSL proposal represents **excellent architectural thinking** about DAZZLE's evolution toward explicit pattern modeling and multi-stack support.

However, the proposal is **premature for immediate implementation**. DAZZLE v0.1.1 just stabilized, and v0.2.0 should focus on production readiness (testing, migrations, monitoring).

**Recommended approach**:
1. **Defer to v0.3.0** and implement incrementally over 3 releases
2. **Start with pattern annotations** (lower risk, faster value)
3. **Validate with design spike** before full DP-DSL architecture
4. **Gather user feedback** at each phase to validate direction
5. **Maintain backwards compatibility** throughout transition

This phased approach balances architectural vision with pragmatic delivery, ensuring DAZZLE evolves sustainably without destabilizing the ecosystem.

---

## References

- **Source Proposal**: `dev_docs/architecture/dazzle_second_bottleneck_dp_dsl_practical_recs_v1.md`
- **Current Roadmap**: `dev_docs/roadmap_v0_2_0.md`
- **DAZZLE DSL Reference**: `docs/DAZZLE_DSL_REFERENCE_0_1.md`
- **IR Documentation**: `docs/DAZZLE_IR_0_1.md`
- **Capabilities Matrix**: `docs/CAPABILITIES_MATRIX.md`

**Document Owner**: DAZZLE Core Team
**Review Cycle**: Revisit before v0.3.0 planning (Q4 2025 / Q1 2026)
**Status**: Approved for phased implementation starting v0.3.0
