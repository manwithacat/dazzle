# Test Generation Strategy - Django Micro Modular Backend

## Overview

The TestGenerator automatically creates comprehensive test suites for Django applications built from DAZZLE DSL specifications.

## Test Organization

```
build/myapp/
  app/
    tests/
      __init__.py
      test_models.py    # Model validation and relationships
      test_views.py     # CRUD operations and view logic
      test_forms.py     # Form validation and constraints
      test_admin.py     # Admin interface functionality
```

## Test Coverage by Generator

### Model Tests (test_models.py)

For each entity, generate tests for:

1. **Basic Creation**
   - Create instance with required fields
   - Verify fields are saved correctly

2. **Field Validation**
   - Required fields (test missing required field)
   - Unique constraints (test duplicate values)
   - Max length (test exceeding max_length)
   - Email validation (test invalid email)
   - Enum validation (test invalid enum value)

3. **Foreign Key Relationships**
   - Create with valid FK reference
   - Test cascade behavior (PROTECT vs SET_NULL vs CASCADE)
   - Test reverse relationships (related_name)

4. **Auto-Generated Fields**
   - UUID primary keys auto-generate
   - Timestamps (auto_add, auto_update)
   - Default values applied correctly

5. **String Representation**
   - __str__ method returns expected format

### View Tests (test_views.py)

For each surface, generate tests for:

1. **List Views**
   - GET returns 200 status
   - Context contains queryset
   - Pagination works
   - Template renders correctly

2. **Detail Views**
   - GET with valid ID returns 200
   - GET with invalid ID returns 404
   - Context contains correct object

3. **Create Views**
   - GET returns 200 (form display)
   - POST with valid data creates object
   - POST with valid data redirects correctly
   - POST with invalid data returns errors
   - Auto-population of missing required FKs works
   - Default objects created when needed

4. **Update Views**
   - GET returns 200 with populated form
   - POST with valid data updates object
   - POST with invalid data returns errors

5. **Delete Views**
   - GET returns 200 (confirmation page)
   - POST deletes object
   - POST redirects correctly

### Form Tests (test_forms.py)

For each form, generate tests for:

1. **Valid Data**
   - Form validates with correct data
   - Form saves correctly

2. **Required Fields**
   - Form invalid without required field
   - Error message displayed

3. **Unique Constraints**
   - Form invalid with duplicate unique field
   - Appropriate error message

4. **Field Validation**
   - Max length enforcement
   - Email format validation
   - Enum value validation

5. **Foreign Key Fields**
   - FK field renders as dropdown
   - Valid FK reference accepted
   - Invalid FK reference rejected

### Admin Tests (test_admin.py)

For each entity admin, generate tests for:

1. **Admin Pages Load**
   - Changelist page returns 200
   - Add page returns 200
   - Change page returns 200

2. **List Display**
   - Configured columns displayed
   - Data renders correctly

3. **Search**
   - Search fields work
   - Results filtered correctly

4. **Filters**
   - Filter options displayed
   - Filtering works correctly

5. **Read-Only Fields**
   - Auto-generated fields are read-only
   - Cannot be edited

## Test Data Strategy

### Fixtures
- Generate minimal required data for FK relationships
- Create reusable test objects in setUp()

### Factory Pattern
- Use simple object creation helpers
- Avoid external dependencies (like factory_boy)

### Test Isolation
- Each test is independent
- Use setUp() and tearDown() properly
- No test depends on another test's data

## Example Generated Test

```python
class TicketModelTest(TestCase):
    """Tests for Ticket model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create(
            email="test@example.com",
            name="Test User"
        )

    def test_create_ticket(self):
        """Test creating a ticket with required fields."""
        ticket = Ticket.objects.create(
            title="Test Ticket",
            description="Test description",
            status="open",
            priority="medium",
            created_by=self.user
        )
        self.assertEqual(ticket.title, "Test Ticket")
        self.assertEqual(ticket.status, "open")
        self.assertEqual(ticket.created_by, self.user)

    def test_title_max_length(self):
        """Test title max_length constraint."""
        long_title = "x" * 201  # Exceeds 200 char limit
        with self.assertRaises(ValidationError):
            ticket = Ticket(
                title=long_title,
                description="Test",
                created_by=self.user
            )
            ticket.full_clean()

    def test_created_by_required(self):
        """Test created_by is required."""
        with self.assertRaises(IntegrityError):
            Ticket.objects.create(
                title="Test",
                description="Test"
                # created_by missing
            )

    def test_created_by_protect(self):
        """Test PROTECT cascade on created_by deletion."""
        ticket = Ticket.objects.create(
            title="Test",
            description="Test",
            created_by=self.user
        )
        with self.assertRaises(ProtectedError):
            self.user.delete()
```

## Test Execution

### During Build
Optional post-build hook to run tests:
```bash
python manage.py test --verbosity=2
```

### Manual Execution
```bash
# Run all tests
python manage.py test

# Run specific test file
python manage.py test app.tests.test_models

# Run specific test class
python manage.py test app.tests.test_models.TicketModelTest

# Run specific test method
python manage.py test app.tests.test_models.TicketModelTest.test_create_ticket
```

## Coverage Goals

- **Model tests**: 100% of fields, constraints, relationships
- **View tests**: All CRUD operations, all surfaces
- **Form tests**: All validation rules, all forms
- **Admin tests**: All admin configurations

## Future Enhancements

1. **Performance tests** - Test query optimization
2. **Security tests** - Test permission/authentication
3. **Integration tests** - Test full workflows
4. **Load tests** - Test under concurrent requests
