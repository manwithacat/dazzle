# Relationships & Queries Architecture

## Overview

Week 11-12 of DNR Phase 2 implements relationships, advanced filtering, sorting, pagination, and full-text search.

## Current State

The repository layer currently:
- Stores `ref` fields as UUID strings (foreign keys)
- Supports basic equality filtering via `filters` parameter
- Has simple page/page_size pagination
- No JOIN capabilities for nested loading
- No sorting options
- No full-text search

## Architecture Goals

### 1. Foreign Key Relationships

**Database Schema Changes**:
- Add FOREIGN KEY constraints to SQLite tables
- Create indexes on foreign key columns automatically
- Handle ON DELETE actions (RESTRICT, CASCADE, SET NULL)

**Repository Changes**:
- Support loading related entities (eager/lazy loading)
- Provide `include` parameter for nested data fetching
- Handle circular references gracefully

### 2. Nested Data Fetching

```python
# Example: Load task with its owner
task = await repo.read(task_id, include=["owner"])
# Returns: {"id": ..., "title": ..., "owner": {"id": ..., "name": ...}}

# Example: Load tasks with owner and project
tasks = await repo.list(include=["owner", "project"])
```

**Implementation Strategy**:
- Parse `include` parameter to determine relations to load
- Use JOINs for efficiency (single query)
- Alternatively, use N+1 queries with batching
- Return nested objects in response

### 3. Advanced Filtering

**Filter Operators**:
```python
# Equality (existing)
filters = {"status": "active"}

# Comparison operators
filters = {"created_at__gt": "2024-01-01", "priority__gte": 5}

# String operators
filters = {"title__contains": "urgent", "title__icontains": "URGENT"}
filters = {"title__startswith": "Bug:", "title__endswith": "!"}

# List operators
filters = {"status__in": ["active", "pending"]}
filters = {"id__not_in": [uuid1, uuid2]}

# Null checks
filters = {"deleted_at__isnull": True}

# Relation filters (via JOIN)
filters = {"owner__name": "John"}
```

**SQL Generation**:
| Operator | SQL |
|----------|-----|
| `__eq` (default) | `field = ?` |
| `__ne` | `field != ?` |
| `__gt` | `field > ?` |
| `__gte` | `field >= ?` |
| `__lt` | `field < ?` |
| `__lte` | `field <= ?` |
| `__contains` | `field LIKE '%?%'` |
| `__icontains` | `LOWER(field) LIKE LOWER('%?%')` |
| `__startswith` | `field LIKE '?%'` |
| `__endswith` | `field LIKE '%?'` |
| `__in` | `field IN (?, ?, ...)` |
| `__not_in` | `field NOT IN (?, ?, ...)` |
| `__isnull` | `field IS NULL` / `field IS NOT NULL` |

### 4. Sorting

```python
# Single field
items = await repo.list(sort="created_at")

# Descending
items = await repo.list(sort="-created_at")

# Multiple fields
items = await repo.list(sort=["priority", "-created_at"])

# Sort by relation field
items = await repo.list(sort="owner__name")
```

### 5. Pagination Enhancements

**Cursor-based pagination** (optional):
```python
# Standard page/page_size (existing)
items = await repo.list(page=1, page_size=20)

# Cursor-based for large datasets
items = await repo.list(cursor="abc123", limit=20)
# Returns: {"items": [...], "next_cursor": "xyz789", "has_more": True}
```

### 6. Full-Text Search

**SQLite FTS5 Integration**:
```python
# Simple search
items = await repo.search("urgent bug fix")

# Search specific fields
items = await repo.search("urgent", fields=["title", "description"])

# Combined with filters
items = await repo.list(search="urgent", filters={"status": "active"})
```

**Implementation**:
1. Create FTS5 virtual table for searchable entities
2. Trigger to sync data between main table and FTS
3. Use MATCH query for search

## Implementation Plan

### Phase 1: Foreign Keys & Basic Relations

1. **Modify DatabaseManager**:
   - Add `FOREIGN KEY` constraints in table creation
   - Add indexes on FK columns
   - Support ON DELETE actions

2. **Add RelationRegistry**:
   - Track relations between entities
   - Build relation metadata from EntitySpec.relations

3. **Extend SQLiteRepository**:
   - Add `include` parameter to `read()` and `list()`
   - Implement JOIN-based loading

### Phase 2: Advanced Filtering

1. **Create QueryBuilder class**:
   - Parse filter operators
   - Generate WHERE clauses
   - Handle type conversions

2. **Update SQLiteRepository.list()**:
   - Accept advanced filter syntax
   - Support relation filters

### Phase 3: Sorting

1. **Update SQLiteRepository.list()**:
   - Add `sort` parameter
   - Support multiple sort fields
   - Handle descending order

### Phase 4: Full-Text Search

1. **Create FTSManager**:
   - Create FTS5 tables
   - Sync data with triggers
   - Provide search API

2. **Update SQLiteRepository**:
   - Add `search` parameter
   - Combine with filters

## File Structure

```
src/dazzle_dnr_back/runtime/
├── repository.py          # Existing - extend with relations
├── query_builder.py       # NEW - filter/sort parsing
├── relation_loader.py     # NEW - nested data loading
├── fts_manager.py         # NEW - full-text search
└── migrations.py          # Existing - extend for FK
```

## API Examples

### REST Endpoints

```
GET /api/tasks?include=owner,project
GET /api/tasks?filter[status]=active&filter[priority__gte]=5
GET /api/tasks?sort=-created_at,priority
GET /api/tasks?search=urgent&filter[status]=active
GET /api/tasks?page=1&page_size=20
```

### Internal Usage

```python
# Repository interface
class SQLiteRepository:
    async def read(
        self,
        id: UUID,
        include: list[str] | None = None,
    ) -> T | None

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: dict[str, Any] | None = None,
        sort: str | list[str] | None = None,
        include: list[str] | None = None,
        search: str | None = None,
    ) -> dict[str, Any]
```

## Test Plan

1. **Foreign Key Tests**:
   - FK constraint creation
   - ON DELETE behavior
   - Invalid reference rejection

2. **Nested Loading Tests**:
   - Single relation loading
   - Multiple relation loading
   - Deep nesting (2 levels)
   - Circular reference handling

3. **Filter Tests**:
   - All operators
   - Type conversions
   - Relation filters
   - Invalid filter handling

4. **Sort Tests**:
   - Single field sort
   - Multiple field sort
   - Descending order
   - Relation field sort

5. **Search Tests**:
   - Basic search
   - Multi-word search
   - Search + filters
   - Empty results

## DSL Integration

```dsl
workspace task_board "Task Board":
  my_tasks:
    source: Task
    filter: owner = current_user and status != "done"
    sort: priority desc, due_date asc
    include: owner, project
    limit: 50
```

Translates to:
```python
await task_repo.list(
    filters={"owner_id": current_user_id, "status__ne": "done"},
    sort=["-priority", "due_date"],
    include=["owner", "project"],
    page_size=50,
)
```
