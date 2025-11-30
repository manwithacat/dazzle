# Support Ticket System

A multi-entity support ticket application demonstrating entity relationships in DAZZLE.

## What's Included

This example demonstrates:
- Multiple related entities (User, Ticket, Comment)
- Foreign key relationships (`ref[Entity]`)
- Enum fields for status and priority
- One-to-many relationships (User -> Tickets, Ticket -> Comments)
- Required vs optional references

## Project Structure

```
support_tickets/
├── dazzle.toml          # Project manifest
├── dsl/                 # DAZZLE DSL modules
│   └── app.dsl         # User, Ticket, and Comment entities
└── build/              # Generated artifacts (after build)
```

## Entity Relationships

```
User
  └── created_by ──> Ticket (many tickets)
  └── assigned_to ──> Ticket (many assigned tickets)
                       └── ticket ──> Comment (many comments)
                                      └── author ──> User
```

## Getting Started

### 1. Validate the DSL

```bash
dazzle validate
```

### 2. Build the project

Build with your chosen stack (selected during clone):

```bash
dazzle build
```

Or use explicit backends:

```bash
dazzle build --backends django_api,openapi,infra_docker
```

This generates artifacts in the `build/` directory.

### 3. Run the Application

#### With Docker (if using infra_docker backend)

```bash
cd build/infra_docker
docker compose up -d
```

#### With Django directly (if using django_api backend)

```bash
cd build/django_api
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser  # Create admin user
python manage.py runserver
```

API will be available at http://localhost:8000

## Understanding the DSL

### Foreign Key References

```dsl
entity Ticket "Support Ticket":
  created_by: ref User required     # Required reference
  assigned_to: ref User             # Optional reference (can be null)
```

### Enum Fields

```dsl
entity Ticket "Support Ticket":
  status: enum[open,in_progress,resolved,closed]=open
  priority: enum[low,medium,high,critical]=medium
```

### Auto Fields

```dsl
entity Ticket "Support Ticket":
  created_at: datetime auto_add      # Set once on creation
  updated_at: datetime auto_update   # Updated on every save
```

## Customizing

### Add a new entity

Add an Attachment entity for ticket attachments:

```dsl
entity Attachment "Attachment":
  id: uuid pk
  ticket: ref Ticket required
  filename: str(255) required
  file_url: str(500) required
  uploaded_by: ref User required
  uploaded_at: datetime auto_add
```

### Add cascading behavior

Modify relationships to specify cascade behavior:

```dsl
entity Comment "Comment":
  ticket: ref Ticket required on_delete=cascade
  author: ref User required on_delete=protect
```

### Add a filter surface

Create a surface to show only high-priority open tickets:

```dsl
surface urgent_tickets "Urgent Tickets":
  uses entity Ticket
  mode: list
  filter: status=open AND priority=critical

  section main "Urgent Tickets":
    field title "Title"
    field created_by "Reporter"
    field assigned_to "Assignee"
    field created_at "Reported"
```

## Next Steps

- Explore the generated Django models in `build/django_api/`
- Check the OpenAPI spec in `build/openapi/openapi.yaml`
- Try adding more entities (tags, categories, etc.)
- Experiment with different surface modes
- Check `LLM_CONTEXT.md` for AI assistant guidance

## Screenshots

### Dashboard
![Dashboard](screenshots/dashboard.png)

### List View
![List View](screenshots/list_view.png)

### Create Form
![Create Form](screenshots/create_form.png)

## Learn More

- Run `dazzle --help` to see all commands
- Use `dazzle lint` for extended validation and suggestions
- Try `dazzle build --diff` to preview changes
- Run `dazzle backends` to see all available backends
