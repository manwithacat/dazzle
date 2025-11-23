# DAZZLE Test DSL Specification

> **📍 Navigation**: This document specifies the test DSL feature and 2-phase implementation.
> For overall version planning, see **`/ROADMAP.md`** (single source of truth).

## Overview

The Test DSL extension allows developers to define domain-specific tests directly in DSL files. These tests describe expected behavior and validate business logic beyond standard CRUD operations.

**Status**: Phase 0 Complete (IR + Parser), Phase 1 planned for v0.2.0, Phase 2 for v0.3.0+

---

## Benefits

### 1. Domain-Specific Testing
Test business logic, not just CRUD:
```dsl
test ticket_cannot_downgrade_priority:
  """Critical tickets cannot be downgraded."""
  setup:
    ticket: create Ticket with priority=critical
  action: update ticket
  data:
    priority: low
  expect:
    status: error
    error_message contains "cannot downgrade"
```

### 2. Living Documentation
Tests serve as executable specifications:
- Non-technical stakeholders can read tests
- Tests document expected behavior
- Changes to requirements update tests

### 3. Cross-Backend Portability
Same test DSL generates tests for any backend:
- Django → Django TestCase
- Express → Jest/Mocha tests
- Go → Go testing package

### 4. Founder-Friendly
Write test scenarios in plain language:
```dsl
test user_can_create_ticket:
  action: create Ticket
  data:
    title: "Bug Report"
    description: "App crashes"
  expect:
    status: success
    created: true
```

---

## Test DSL Syntax

### Basic Structure

```dsl
test test_name:
  """Human-readable description."""
  [setup:]
    [variable: create Entity with field=value, ...]
  action: <create|update|delete|get> Target
  [data:]
    field: value
  [filter:]
    field: value
  [search:]
    query: "text"
  [order_by: "field"]
  expect:
    <assertion>
    <assertion>
```

### Components

#### 1. Test Name
Unique identifier for the test:
```dsl
test user_email_uniqueness:
```

#### 2. Description (Optional)
Human-readable explanation:
```dsl
  """Test that duplicate emails are rejected."""
```

#### 3. Setup (Optional)
Create objects before test action:
```dsl
  setup:
    user: create User with email="test@example.com", name="Test User"
    ticket: create Ticket with title="Test", created_by=user
```

#### 4. Action (Required)
The operation being tested:
```dsl
  action: create Ticket
  action: update ticket
  action: delete user
  action: get Task
```

#### 5. Data (For Create/Update)
Data for the action:
```dsl
  data:
    title: "New Ticket"
    priority: "high"
    assigned_to: user
```

#### 6. Filter (For Get)
Filter criteria:
```dsl
  filter:
    status: "todo"
    priority: "high"
```

#### 7. Search (For Get)
Search query:
```dsl
  search:
    query: "Django"
```

#### 8. Order By (For Get)
Ordering:
```dsl
  order_by: "-priority"  # Descending
  order_by: "created_at" # Ascending
```

#### 9. Expect (Required)
Assertions about the outcome:
```dsl
  expect:
    status: success
    created: true
    field title equals "New Ticket"
    count equals 5
```

---

## Assertions

### Status Assertions
```dsl
status: success  # Operation succeeded
status: error    # Operation failed
```

### Created Assertions
```dsl
created: true   # Object was created
created: false  # Object was not created
```

### Field Assertions
```dsl
field <name> equals <value>
field <name> not_equals <value>
field <name> greater_than <value>
field <name> less_than <value>
field <name> contains <value>
field <name> not_contains <value>
```

**Examples**:
```dsl
field status equals "open"
field priority not_equals "low"
field created_at greater_than field updated_at
field title contains "Bug"
```

### Error Assertions
```dsl
error_message contains "text"
error_message equals "exact text"
```

### Count Assertions
```dsl
count equals 5
count greater_than 0
count less_than 10
```

### Collection Assertions
```dsl
first field <name> equals <value>
last field <name> equals <value>
```

---

## Examples

### Example 1: Basic Creation Test

```dsl
test create_task_with_defaults:
  """Test task creation uses default values."""
  action: create Task
  data:
    title: "Test Task"
    description: "Test"
  expect:
    status: success
    created: true
    field status equals "todo"
    field priority equals "medium"
```

### Example 2: Validation Test

```dsl
test email_required:
  """Test that email is required for users."""
  action: create User
  data:
    name: "Test User"
    # email missing
  expect:
    status: error
    error_message contains "email is required"
```

### Example 3: Relationship Test

```dsl
test user_deletion_protects_tickets:
  """Test that users with tickets cannot be deleted."""
  setup:
    user: create User with email="test@example.com", name="Test"
    ticket: create Ticket with title="Test", created_by=user
  action: delete user
  expect:
    status: error
    error_message contains "has tickets"
```

### Example 4: Filtering Test

```dsl
test filter_high_priority_tasks:
  """Test filtering tasks by priority."""
  setup:
    task1: create Task with title="High", priority="high"
    task2: create Task with title="Low", priority="low"
  action: get Task
  filter:
    priority: "high"
  expect:
    count equals 1
    first field title equals "High"
```

### Example 5: Business Logic Test

```dsl
test ticket_status_workflow:
  """Test ticket progresses through status workflow."""
  setup:
    user: create User with email="test@example.com", name="Test"
    ticket: create Ticket with title="Test", created_by=user, status="open"
  action: update ticket
  data:
    status: "in_progress"
    assigned_to: user
  expect:
    status: success
    field status equals "in_progress"
    field assigned_to equals user
    field updated_at greater_than field created_at
```

---

## Generated Test Output

### From DSL:
```dsl
test task_creation_with_defaults:
  action: create Task
  data:
    title: "Test Task"
    description: "Test"
  expect:
    status: success
    field status equals "todo"
```

### To Python (Django):
```python
def test_task_creation_with_defaults(self):
    """Test task creation uses default values (from DSL)."""
    # Execute action
    task = Task.objects.create(
        title="Test Task",
        description="Test"
    )

    # Verify expectations
    self.assertIsNotNone(task)
    self.assertEqual(task.status, "todo")
```

### To JavaScript (Express/Jest):
```javascript
test('task_creation_with_defaults', async () => {
  // Test task creation uses default values (from DSL)

  // Execute action
  const response = await request(app)
    .post('/api/tasks')
    .send({
      title: 'Test Task',
      description: 'Test'
    });

  // Verify expectations
  expect(response.status).toBe(201);
  expect(response.body.status).toBe('todo');
});
```

---

## Implementation Status

### ✅ Complete

1. **IR Types** (`core/ir.py`):
   - `TestActionKind` - Action types
   - `TestAssertionKind` - Assertion types
   - `TestComparisonOperator` - Comparison operators
   - `TestSetupStep` - Setup object creation
   - `TestAction` - Main test action
   - `TestAssertion` - Test expectations
   - `TestSpec` - Complete test definition
   - `AppSpec.tests` - List of tests
   - `AppSpec.get_test()` - Helper method

2. **Example DSL Files**:
   - `examples/simple_task/dsl/tests.dsl` - 20+ test examples
   - `examples/support_tickets/dsl/tests.dsl` - 25+ test examples

3. **Documentation**:
   - Test DSL specification (this file)
   - Testing implementation guide
   - Test generation strategy

### ⏳ Pending

1. **Parser Updates** (`core/parser/`):
   - Recognize `test` keyword
   - Parse test blocks
   - Parse setup steps
   - Parse action syntax
   - Parse expect assertions
   - Build TestSpec IR
   - Add tests to AppSpec

2. **TestGenerator Enhancements** (`backends/django_micro_modular/generators/tests.py`):
   - Read `spec.tests`
   - Generate test methods from TestSpec
   - Translate setup steps to Python
   - Translate actions to Django operations
   - Translate assertions to test assertions
   - Handle variable references
   - Handle relationships
   - Generate setUp/tearDown methods

3. **Error Handling**:
   - Validate test references (entities, fields)
   - Type checking for assertions
   - Circular dependency detection
   - Invalid operator detection

---

## Parser Implementation Roadmap

### Phase 1: Lexer Updates
Add tokens for test DSL:
```python
# In lexer
TEST = "test"
SETUP = "setup"
ACTION = "action"
DATA = "data"
FILTER = "filter"
SEARCH = "search"
ORDER_BY = "order_by"
EXPECT = "expect"
STATUS = "status"
CREATED = "created"
FIELD = "field"
COUNT = "count"
```

### Phase 2: Grammar Updates
Add test definition rules:
```ebnf
test_definition = "test" IDENTIFIER ":" test_body

test_body = [STRING]  # description
           [setup_block]
           action_block
           [data_block]
           [filter_block]
           [search_block]
           [order_by_clause]
           expect_block

setup_block = "setup" ":" (setup_step)+
setup_step = IDENTIFIER ":" "create" IDENTIFIER "with" assignments

action_block = "action" ":" action_kind target
action_kind = "create" | "update" | "delete" | "get"

data_block = "data" ":" (assignment)+
filter_block = "filter" ":" (assignment)+
search_block = "search" ":" assignment

expect_block = "expect" ":" (assertion)+
assertion = status_assertion
         | created_assertion
         | field_assertion
         | error_assertion
         | count_assertion
```

### Phase 3: AST Updates
Add test nodes to AST:
```python
class TestDefinition(ASTNode):
    name: str
    description: Optional[str]
    setup_steps: List[SetupStep]
    action: ActionStatement
    data: Dict[str, Any]
    filter: Dict[str, Any]
    expect: List[Assertion]
```

### Phase 4: IR Builder Updates
Translate AST to TestSpec:
```python
def build_test_spec(test_node: TestDefinition) -> TestSpec:
    return TestSpec(
        name=test_node.name,
        description=test_node.description,
        setup_steps=build_setup_steps(test_node.setup_steps),
        action=build_test_action(test_node.action, test_node.data),
        assertions=build_assertions(test_node.expect)
    )
```

---

## TestGenerator Implementation Roadmap

### Step 1: Read Tests from Spec
```python
def _generate_dsl_tests(self) -> List[str]:
    """Generate test methods from DSL test definitions."""
    lines = []

    for test_spec in self.spec.tests:
        lines.extend(self._generate_test_from_spec(test_spec))
        lines.append('')

    return lines
```

### Step 2: Generate Test Method
```python
def _generate_test_from_spec(self, test_spec: TestSpec) -> List[str]:
    lines = [
        f'def test_{test_spec.name}_from_dsl(self):',
        f'    """{test_spec.description or test_spec.name} (from DSL)."""',
    ]

    # Generate setup
    if test_spec.setup_steps:
        lines.extend(self._generate_setup_from_spec(test_spec.setup_steps))

    # Generate action
    lines.extend(self._generate_action_from_spec(test_spec.action))

    # Generate assertions
    lines.extend(self._generate_assertions_from_spec(test_spec.assertions))

    return lines
```

### Step 3: Translate Assertions
```python
def _generate_assertions_from_spec(self, assertions: List[TestAssertion]) -> List[str]:
    lines = []

    for assertion in assertions:
        if assertion.kind == TestAssertionKind.STATUS:
            if assertion.expected_value == "success":
                lines.append('    # Assert success')
            else:
                lines.append('    # Assert error')

        elif assertion.kind == TestAssertionKind.FIELD:
            field = assertion.field_name
            op = assertion.operator
            value = assertion.expected_value

            if op == TestComparisonOperator.EQUALS:
                lines.append(f'    self.assertEqual(obj.{field}, {value})')
            # ... other operators

    return lines
```

---

## Implementation Roadmap (Revised 2025-11-23)

### ✅ Phase 0: Foundation (COMPLETE)
**Status**: Done
**Completed**: November 2025

- ✅ IR types added (`TestSpec`, `TestAction`, `TestAssertion`, etc.)
- ✅ Parser implementation (`parse_test()` in dsl_parser.py)
- ✅ Example DSL files created (`examples/*/dsl/tests.dsl`)
- ✅ Complete documentation (this file)

**What Works**: DSL test files can be written and parsed into IR

**What Doesn't**: No stack generators read or use TestSpec yet

---

### 🎯 Two-Phase Implementation Strategy

Based on current project priorities and v0.2.0 roadmap analysis, test implementation is split into two phases:

#### **Phase 1: Basic Test Infrastructure (v0.2.0)**
**Target**: Q1 2026
**Priority**: HIGH
**Focus**: Generate standard framework tests for generated code quality

**Scope**:
- Generate Jest tests for Express stacks (routes, models)
- Generate pytest tests for Django stacks (models, views, APIs)
- Basic CRUD test coverage
- Test configuration and setup files
- Integration with npm/pytest test runners

**Out of Scope**: DSL-to-test translation (deferred to Phase 2)

**Generated Output Example**:
```javascript
// Auto-generated by stack, NOT from test DSL
describe('Task Model', () => {
  it('should create a task', async () => {
    const task = await Task.create({title: "Test"});
    expect(task.title).toBe("Test");
  });
});
```

**Deliverables**:
- Test generators for Django stacks
- Test generators for Express stacks
- Test templates and fixtures
- Test runner configuration
- Documentation for running tests

**See**: `dev_docs/roadmap_v0_2_0.md` for detailed v0.2.0 scope

---

#### **Phase 2: DSL Test Translation (v0.3.0+)**
**Target**: Q2 2026
**Priority**: MEDIUM
**Focus**: Translate test DSL to framework tests

**Scope**:
- Activate existing TestSpec IR in generators
- Read `spec.tests` in stack generators
- Translate test DSL → Jest/pytest tests
- Support all assertion types
- Validate test references
- Handle setup steps and relationships
- Error handling and diagnostics

**Generated Output Example**:
```javascript
// Generated FROM test DSL
test('task_creation_with_defaults_from_dsl', async () => {
  // From: test task_creation_with_defaults in dsl/tests.dsl
  const response = await request(app)
    .post('/api/tasks')
    .send({title: 'Test Task', description: 'Test'});

  expect(response.status).toBe(201);
  expect(response.body.status).toBe('todo'); // From: expect field status equals "todo"
  expect(response.body.priority).toBe('medium'); // From: expect field priority equals "medium"
});
```

**Deliverables**:
- TestSpec → Django test translation
- TestSpec → Express test translation
- Assertion translation for all operators
- Setup step translation
- Test validation rules
- Complete integration with build pipeline
- Updated documentation

**Dependencies**:
- Phase 1 must be complete (test infrastructure exists)
- Stack generators must support plugin architecture for DSL tests

---

### Timeline Summary

| Phase | Version | Status | Timeline | Effort |
|-------|---------|--------|----------|--------|
| Phase 0 | v0.1.0 | ✅ Complete | Nov 2025 | Done |
| Phase 1 | v0.2.0 | 📋 Planned | Q1 2026 | 2-3 weeks |
| Phase 2 | v0.3.0+ | 📋 Future | Q2 2026 | 3-4 weeks |

---

## Usage (Future)

Once implemented, usage will be:

```bash
# Write tests in DSL
vim dsl/tests.dsl

# Validate DSL (includes tests)
dazzle validate

# Build (generates tests automatically)
dazzle build

# Run ALL tests (generated + DSL)
cd build/myapp
python manage.py test

# Output:
# test_create_task ........................ ok
# test_task_creation_with_defaults_from_dsl .. ok  ← From DSL!
# test_email_required_from_dsl .............. ok  ← From DSL!
# Ran 62 tests in 3.245s
# OK
```

---

## Design Decisions

### 1. Separate Test Files
Tests in `dsl/tests.dsl` separate from main DSL for:
- Clarity
- Optional inclusion
- Large test suites management

### 2. Immutable IR
TestSpec is frozen (Pydantic) for:
- Thread safety
- Cacheable
- Predictable behavior

### 3. Backend-Agnostic IR
TestSpec doesn't assume Django/Express/etc:
- Same IR works for all backends
- Backend decides implementation details
- Portable tests

### 4. Explicit Over Implicit
DSL requires explicit expectations:
```dsl
# Good - explicit
expect:
  status: success
  field status equals "open"

# Bad - implicit (not supported)
expect:
  # Implicitly assumes success?
```

---

## Conclusion

**Phase 3 Status**: IR Complete, Parser & Generator Pending

**What's Done**:
- ✅ Complete IR types for tests
- ✅ Example test DSL files
- ✅ Full documentation

**What's Next**:
- ⏳ Parser updates to recognize test blocks
- ⏳ TestGenerator enhancements to translate DSL → Python
- ⏳ Validation and error handling

**Current Capability**:
- Tests can be defined in DSL (syntax demonstrated)
- Manual translation possible (for experimentation)
- Foundation ready for parser implementation

**When Complete**:
- Automatic test generation from DSL
- Domain-specific validation
- Cross-backend portability
- Founder-friendly test specification
