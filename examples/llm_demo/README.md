# Recipe Manager - LLM Analysis Demo

This example demonstrates DAZZLE's LLM-assisted specification analysis feature.

## What This Demonstrates

1. **Natural Language Spec** → **Structured Analysis**
2. **State Machine Detection** (Recipe status workflow)
3. **CRUD Completeness Analysis**
4. **Business Rules Extraction**
5. **Clarifying Questions Generation**
6. **DSL Code Generation**

## Quick Start

### Prerequisites

```bash
# Install DAZZLE with LLM support
pip install "dazzle[llm]"

# Set your Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...
```

### Analyze the Spec

```bash
# From this directory
dazzle analyze-spec SPEC.md
```

Expected output:
```
🔍 Analyzing specification with anthropic (claude-3-5-sonnet-20241022)...

============================================================
📊 Specification Analysis Results
============================================================

🔄 State Machines: 1
   • Recipe.status: Not Tried, Want to Try, Tried, Favorite
     - 3-4 transitions found

📋 Entities Analyzed: 1
   • Recipe: All CRUD operations found

📏 Business Rules: 6-8
   • validation: 4-5
   • constraint: 2-3

❓ Clarifying Questions: 3-5
   • State Machine (medium): 1-2 questions
   • CRUD Completeness (low): 1-2 questions
   • Business Rules (medium): 1 question

📈 Coverage:
   • State Machines: 75-100%
   • CRUD Operations: 100%
```

### Generate DSL

```bash
dazzle analyze-spec SPEC.md --generate-dsl
```

This creates `dsl/generated.dsl` with:
- Recipe entity with all fields
- State machine for status
- All CRUD surfaces (list, detail, create, edit)
- Business rules documentation

### Build the App

```bash
# Validate the generated DSL
dazzle validate

# Build Django backend
dazzle build

# Run the app
cd build/llm_demo
python manage.py migrate
python manage.py runserver
```

Visit `http://localhost:8000` to see your recipe manager!

## What the LLM Found

### State Machine

The LLM identifies a clear state workflow for Recipe.status:

```
Not Tried → Want to Try → Tried → Favorite
```

With possible direct transitions:
- Not Tried → Favorite (for family recipes)
- Want to Try → Favorite (if you loved it on first try)

### CRUD Analysis

**Recipe entity:**
- ✅ Create: "Create new recipes" (SPEC.md:32)
- ✅ Read: "View recipe details" (SPEC.md:50)
- ✅ Update: "Update recipes" (SPEC.md:59)
- ✅ Delete: "Delete recipes" (SPEC.md:72)
- ✅ List: "View all my recipes" (SPEC.md:38)

**Coverage: 100%** - All CRUD operations explicitly mentioned!

### Business Rules Extracted

1. **Validation**:
   - Title: required, max 200 chars, must be unique
   - Ingredients: required
   - Instructions: required
   - Times: must be positive numbers

2. **Constraints**:
   - Category: must be one of 5 values
   - Status: must be one of 4 values

3. **Auto-fields**:
   - Created At: auto-set on creation
   - Updated At: auto-update on edit

### Clarifying Questions Generated

1. **State Machine**:
   - "Can recipes move backward in status? (e.g., Favorite → Tried)"
   - "Is there a specific order, or can users jump directly to any status?"

2. **CRUD**:
   - "Should search be case-sensitive?"
   - "Should deleted recipes be soft-deleted (archived) or hard-deleted?"

3. **Features**:
   - "Should recipes be printable?"
   - "Should there be a duplicate recipe check?"

## Generated DSL Preview

```dsl
module llm_demo

app llm_demo "Recipe Manager"

# ============================================================================
# ENTITIES
# ============================================================================

entity Recipe "Recipe":
  id: uuid pk
  title: str(200) required unique
  description: text
  category: enum[breakfast,lunch,dinner,dessert,snack]=dinner
  ingredients: text required
  instructions: text required
  prep_time: int
  cook_time: int
  servings: int
  status: enum[not_tried,want_to_try,tried,favorite]=not_tried
  created_at: datetime auto_add
  updated_at: datetime auto_update

# ============================================================================
# SURFACES
# ============================================================================

surface recipe_list "Recipe List":
  uses entity Recipe
  mode: list

  section main "Recipes":
    field title "Title"
    field category "Category"
    field status "Status"
    field created_at "Added"

surface recipe_detail "Recipe Detail":
  uses entity Recipe
  mode: view

  section main "Recipe Details":
    field title "Title"
    field description "Description"
    field category "Category"
    field ingredients "Ingredients"
    field instructions "Instructions"
    field prep_time "Prep Time"
    field cook_time "Cook Time"
    field servings "Servings"
    field status "Status"

surface recipe_create "New Recipe":
  uses entity Recipe
  mode: create

  section main "Create Recipe":
    field title "Title"
    field description "Description"
    field category "Category"
    field ingredients "Ingredients"
    field instructions "Instructions"
    field prep_time "Prep Time (minutes)"
    field cook_time "Cook Time (minutes)"
    field servings "Servings"

surface recipe_edit "Edit Recipe":
  uses entity Recipe
  mode: edit

  section main "Edit Recipe":
    field title "Title"
    field description "Description"
    field category "Category"
    field ingredients "Ingredients"
    field instructions "Instructions"
    field prep_time "Prep Time (minutes)"
    field cook_time "Cook Time (minutes)"
    field servings "Servings"
    field status "Status"
```

## Customization

After generation, you might want to:

1. **Add relationships**: If you later add a `User` entity
2. **Refine field types**: Change `text` to `richtext` for instructions
3. **Add filters**: Specify which fields are filterable in list surface
4. **Add search**: Enable search on title and ingredients
5. **Customize surfaces**: Reorder fields, add sections, adjust labels

## Cost

**Spec size**: ~6KB
**Estimated cost**: ~$0.09-$0.12 per analysis
**Analysis time**: 8-12 seconds

## Next Steps

1. Review and customize the generated DSL
2. Add any relationships (if multi-user)
3. Run `dazzle validate`
4. Run `dazzle build`
5. Customize Django templates if needed
6. Deploy!

## Comparison

### Without LLM Assistance
- Write ~150 lines of DSL manually
- Understand DSL syntax fully
- Remember all field types and modifiers
- **Time: 1-2 hours**

### With LLM Assistance
- Write natural language spec: 10 minutes
- Review analysis: 2 minutes
- Answer 3-5 questions: 3 minutes
- Review generated DSL: 5 minutes
- **Time: 20 minutes**

**6x faster!** ⚡

---

**Try it yourself!** Modify `SPEC.md` and re-analyze to see how the LLM adapts.
