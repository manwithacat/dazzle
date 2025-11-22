# Recipe Manager - Product Specification

**Project Type**: Personal Recipe Management Tool
**Target Users**: Home cooks who want to organize their recipes
**Deployment**: Single-user web application

---

## Project Overview

I want a simple recipe management app where I can store my favorite recipes, organize them by category, and mark which ones I've tried. I should be able to search for recipes and see ingredient lists at a glance.

Nothing complex - just a clean way to keep track of my recipes instead of having them scattered across bookmarks and paper notes.

---

## Core Features

### Recipe Management

Each recipe should have:
- **Title** (required) - Name of the dish (e.g., "Chocolate Chip Cookies")
- **Description** (optional) - Brief description of the dish
- **Category** - Type of dish: Breakfast, Lunch, Dinner, Dessert, Snack
- **Ingredients** (required) - List of ingredients with quantities
- **Instructions** (required) - Step-by-step cooking instructions
- **Prep Time** (optional) - How long to prepare (in minutes)
- **Cook Time** (optional) - How long to cook (in minutes)
- **Servings** (optional) - Number of servings it makes
- **Status** - Whether I've tried it: Not Tried, Want to Try, Tried, Favorite
- **Timestamps** - When I added it and last updated it

### User Stories

**As a user, I want to:**

1. **Create new recipes**
   - Enter title, category, ingredients, and instructions
   - Optionally add prep time, cook time, and servings
   - Recipe starts in "Not Tried" status
   - Save to my collection

2. **View all my recipes**
   - See a list of recipes with title, category, and status
   - Filter by category (Breakfast, Lunch, Dinner, etc.)
   - Filter by status (favorites, want to try, etc.)
   - Search by recipe name or ingredients
   - Sort by recently added or alphabetically

3. **View recipe details**
   - See full recipe with all information
   - Read ingredients list clearly
   - Follow step-by-step instructions
   - See prep/cook times and servings
   - Check when I added it

4. **Update recipes**
   - Edit any recipe information
   - Change status (mark as tried, favorite, etc.)
   - Update ingredients or instructions as I refine them
   - Adjust servings or times

5. **Mark recipe status**
   - Move from "Not Tried" → "Want to Try" (when I find interesting recipes)
   - Move from "Want to Try" → "Tried" (after making it)
   - Move from "Tried" → "Favorite" (if I loved it)
   - Or directly mark as "Favorite" if it's a family recipe

6. **Delete recipes**
   - Remove recipes I don't want anymore
   - Get confirmation before deleting

---

## Data Model

### Recipe Object

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| ID | UUID | Yes | Auto-generated | Unique identifier |
| Title | Text (max 200 chars) | Yes | - | Recipe name |
| Description | Long text | No | - | Brief description |
| Category | Choice | Yes | "Dinner" | Breakfast, Lunch, Dinner, Dessert, Snack |
| Ingredients | Long text | Yes | - | List of ingredients |
| Instructions | Long text | Yes | - | Step-by-step directions |
| Prep Time | Integer (minutes) | No | - | Preparation time |
| Cook Time | Integer (minutes) | No | - | Cooking time |
| Servings | Integer | No | - | Number of servings |
| Status | Choice | Yes | "Not Tried" | Not Tried, Want to Try, Tried, Favorite |
| Created At | Timestamp | Yes | Auto | When recipe was added |
| Updated At | Timestamp | Yes | Auto | Last modification time |

---

## User Interface

### Pages I Need

1. **Recipe List Page** (Home/Main page)
   - Table or card grid showing: Title, Category, Status, Prep+Cook Time
   - "Add New Recipe" button at the top
   - Filter dropdowns: Category, Status
   - Search bar: Search by title or ingredients
   - Actions for each recipe: View, Edit, Delete

2. **Recipe Detail Page**
   - Display recipe title prominently
   - Show category and status
   - Ingredients section (clearly formatted list)
   - Instructions section (numbered steps)
   - Times and servings info
   - Buttons: Edit, Delete, Back to List

3. **Create Recipe Form**
   - Fields: Title (required), Description, Category dropdown
   - Ingredients textarea
   - Instructions textarea
   - Prep Time, Cook Time, Servings (optional number fields)
   - Category defaults to "Dinner"
   - Status automatically set to "Not Tried"
   - Save button returns to recipe list

4. **Edit Recipe Form**
   - Same as create, but with all current values pre-filled
   - Can update status dropdown (Not Tried → Want to Try → Tried → Favorite)
   - Save button returns to detail view
   - Cancel option to go back without saving

---

## Business Rules

- Title is required and must be unique (can't have duplicate recipe names)
- Ingredients and instructions are required (can't save without them)
- Category must be one of the 5 allowed values
- Status must be one of the 4 allowed values
- Times and servings must be positive numbers if provided
- When recipe is updated, the "Updated At" timestamp updates automatically

---

## Questions for Clarification

- Should recipes be printable (print-friendly view)?
- Should I be able to rate recipes (1-5 stars)?
- Should I track when I last made each recipe?
- Should ingredients support quantities/measurements parsing?
- Should there be a "shopping list" feature?

---

## Out of Scope (for now)

- Multi-user features / sharing recipes
- Photo uploads for recipes
- Meal planning calendar
- Nutritional information
- Recipe import from websites
- Mobile app (web-only for now)

---

## Technical Notes

- Simple deployment (Heroku, Railway, etc.)
- No complex authentication needed (personal use)
- Responsive design (works on tablet for kitchen use)
- Fast search/filter (should be near-instant)
