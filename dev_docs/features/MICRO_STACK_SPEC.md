# Micro Stack Specification

## Overview

The "micro" stack is designed to be the simplest possible DAZZLE deployment:
- Single Django application (no separate frontend)
- SQLite database (no external database server)
- Direct Python hosting (no Docker/containers)
- Easy deployment to PaaS platforms (Heroku, Vercel, PythonAnywhere, Railway)

**Perfect for**:
- First-time DAZZLE users
- Learning and tutorials
- Prototyping and MVPs
- Small internal tools
- Personal projects

## Stack Configuration

```python
"micro": StackPreset(
    name="micro",
    description="Single Django app with SQLite (easiest to deploy on Heroku/Vercel)",
    backends=["django_micro"],
    example_dsl="simple_task",
)
```

## Backend: `django_micro`

### Purpose

Generate a complete, self-contained Django application that:
- Includes models, admin, views, and templates
- Uses Django's built-in template system (no separate frontend framework)
- Configured for SQLite (no PostgreSQL/MySQL required)
- Ready to deploy with minimal configuration

### Output Structure

```
build/django_micro/
├── manage.py
├── requirements.txt
├── runtime.txt              # For Heroku
├── Procfile                 # For Heroku
├── vercel.json             # For Vercel
├── .env.example
├── README.md               # Deployment instructions
├── app/                    # Main Django app
│   ├── __init__.py
│   ├── settings.py         # SQLite, simple config
│   ├── urls.py
│   ├── wsgi.py
│   ├── asgi.py
│   └── models.py           # All entities as models
├── core/                   # Generated app
│   ├── __init__.py
│   ├── models.py           # Entity models
│   ├── admin.py            # Admin configuration
│   ├── views.py            # CRUD views
│   ├── urls.py             # URL patterns
│   ├── forms.py            # Surface-based forms
│   └── templates/
│       └── core/
│           ├── base.html
│           ├── entity_list.html
│           ├── entity_detail.html
│           ├── entity_form.html
│           └── ...
└── static/
    ├── css/
    │   └── style.css       # Minimal styling
    └── js/
        └── app.js          # Optional enhancements
```

### Key Features

#### 1. SQLite Configuration

`settings.py`:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Simple static files config
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Simple media files config
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
```

#### 2. Model Generation

From DAZZLE entities to Django models:

```dsl
entity Task:
  id: uuid pk
  title: str(200) required
  completed: bool=false
  created_at: datetime auto_add
```

Generates:

```python
# core/models.py
import uuid
from django.db import models

class Task(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Task"
        verbose_name_plural = "Tasks"

    def __str__(self):
        return self.title
```

#### 3. Admin Configuration

Automatic admin registration:

```python
# core/admin.py
from django.contrib import admin
from .models import Task

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'completed', 'created_at')
    list_filter = ('completed', 'created_at')
    search_fields = ('title',)
    readonly_fields = ('id', 'created_at')
```

#### 4. Views from Surfaces

DAZZLE surfaces → Django views:

```dsl
surface task_list "Task List":
  uses entity Task
  mode: list
  
  section main:
    field title "Title"
    field completed "Done"
```

Generates:

```python
# core/views.py
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from .models import Task
from .forms import TaskForm

class TaskListView(ListView):
    model = Task
    template_name = 'core/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 20

class TaskCreateView(CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'core/task_form.html'
    success_url = '/tasks/'
```

#### 5. Templates

Bootstrap-based templates (no build step required):

```html
<!-- core/templates/core/task_list.html -->
{% extends "base.html" %}

{% block content %}
<div class="container mt-4">
  <h1>Task List</h1>
  
  <a href="{% url 'task_create' %}" class="btn btn-primary mb-3">
    Add Task
  </a>
  
  <div class="list-group">
    {% for task in tasks %}
    <a href="{% url 'task_detail' task.pk %}" class="list-group-item">
      <h5>{{ task.title }}</h5>
      <small>{% if task.completed %}✓ Done{% else %}Pending{% endif %}</small>
    </a>
    {% empty %}
    <p>No tasks yet.</p>
    {% endfor %}
  </div>
</div>
{% endblock %}
```

#### 6. Forms from Surfaces

Generate Django forms from create/edit surfaces:

```python
# core/forms.py
from django import forms
from .models import Task

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'completed']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'completed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
```

### Deployment Configuration Files

#### requirements.txt
```
Django>=4.2,<5.0
gunicorn>=21.0
whitenoise>=6.5
python-dotenv>=1.0
```

#### Procfile (Heroku)
```
web: gunicorn app.wsgi --bind 0.0.0.0:$PORT
release: python manage.py migrate
```

#### runtime.txt (Heroku)
```
python-3.11.7
```

#### vercel.json (Vercel)
```json
{
  "builds": [
    {
      "src": "app/wsgi.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "app/wsgi.py"
    }
  ]
}
```

### Deployment Instructions

Generated `README.md` in build directory:

```markdown
# DAZZLE Micro Stack - Simple Task

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run migrations:
   ```bash
   python manage.py migrate
   ```

3. Create superuser:
   ```bash
   python manage.py createsuperuser
   ```

4. Run development server:
   ```bash
   python manage.py runserver
   ```

5. Visit:
   - App: http://localhost:8000/
   - Admin: http://localhost:8000/admin/

## Deploy to Heroku

1. Install Heroku CLI
2. Login: `heroku login`
3. Create app: `heroku create my-app`
4. Deploy:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git push heroku main
   ```
5. Run migrations: `heroku run python manage.py migrate`
6. Create admin: `heroku run python manage.py createsuperuser`

## Deploy to Vercel

1. Install Vercel CLI: `npm i -g vercel`
2. Deploy: `vercel`
3. Follow prompts

## Deploy to PythonAnywhere

1. Upload files to PythonAnywhere
2. Create virtual environment
3. Install requirements: `pip install -r requirements.txt`
4. Configure WSGI file
5. Run migrations in Bash console

## Configuration

Edit `.env` file:
```
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=yourdomain.com
```
```

## Default Stack

The "micro" stack is the default for `dazzle demo`:

```bash
# These are equivalent:
dazzle demo
dazzle demo micro

# All create the simplest possible setup
```

## User Experience Flow

### First-time User Journey

1. **Install DAZZLE**:
   ```bash
   pip install dazzle
   ```

2. **Create Demo** (no arguments needed):
   ```bash
   dazzle demo
   ```
   
   Output shows:
   - "Using default: 'micro'"
   - What micro stack includes
   - Why it's good for beginners
   - Links to other stacks

3. **Run Locally**:
   ```bash
   cd micro-demo
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py runserver
   ```

4. **Deploy** (when ready):
   - Follow README for Heroku/Vercel
   - No Docker or infrastructure knowledge needed

5. **Explore Other Stacks**:
   - `dazzle demo --list` shows all options
   - Each demo completion shows breadcrumbs to other stacks

### Progressive Disclosure

The demo output progressively discloses complexity:

**For Micro Stack**:
```
✓ Demo created: ./micro-demo

This is the simplest DAZZLE setup:
  - Single Django application
  - SQLite database (no separate DB server needed)
  - Easy to deploy on Heroku, Vercel, or PythonAnywhere

Perfect for:
  - Learning DAZZLE
  - Prototyping
  - Small projects

------------------------------------------------------------
Other available stacks:
  dazzle demo --list           # See all stack options

Popular choices:
  dazzle demo openapi_only     # Just OpenAPI spec (no code)
  dazzle demo api_only         # Django API + Docker
  dazzle demo django_next      # Full-stack with Next.js frontend
============================================================
```

## Implementation Tasks

### Phase 1: Core Backend (Required for MVP)
- [ ] Create `backends/django_micro/` module
- [ ] Implement model generation from entities
- [ ] Generate admin configuration
- [ ] Create basic views (ListView, DetailView, CreateView, UpdateView)
- [ ] Generate forms from surfaces
- [ ] Create base templates with Bootstrap
- [ ] Generate settings.py with SQLite config
- [ ] Create requirements.txt
- [ ] Generate README with deployment instructions

### Phase 2: Deployment Support
- [ ] Add Heroku configuration (Procfile, runtime.txt)
- [ ] Add Vercel configuration (vercel.json)
- [ ] Add Railway configuration
- [ ] Add PythonAnywhere instructions
- [ ] Environment variable handling (.env support)
- [ ] Static files configuration (WhiteNoise)

### Phase 3: Polish
- [ ] Better templates with HTMX for interactivity (no build step)
- [ ] Improved styling (Tailwind CDN or Bootstrap)
- [ ] Form validation and error display
- [ ] Success messages
- [ ] Pagination
- [ ] Search and filters
- [ ] Mobile-responsive design

### Phase 4: Advanced Features (Optional)
- [ ] Authentication/authorization views
- [ ] Password reset flows
- [ ] API endpoints (Django REST framework optional)
- [ ] Export functionality (CSV, PDF)
- [ ] Email configuration
- [ ] Celery task support (optional)

## Benefits

### For New Users
- **No Docker knowledge required**
- **No database setup** - SQLite works out of the box
- **No frontend build tools** - Django templates only
- **Fast feedback loop** - Edit DSL, rebuild, refresh browser
- **Easy deployment** - One-click on most PaaS platforms

### For Learning
- **Clear path from DSL to code** - Easy to understand generated code
- **Progressive complexity** - Start simple, add features as needed
- **Real application** - Not just specs, actual working app
- **Breadcrumbs to advanced stacks** - Natural progression path

### For Prototyping
- **Fast iteration** - Minimal setup time
- **Self-contained** - No external dependencies
- **Easy sharing** - Deploy and share URL quickly
- **Real data** - SQLite persists between runs

## Success Metrics

- 90%+ of new users can deploy their first DAZZLE app within 15 minutes
- Clear path to more complex stacks when ready
- Reduced support questions about Docker/infrastructure
- Higher completion rate for tutorials

## Future Enhancements

- **Hot reload** in development
- **Automatic HTTPS** with Let's Encrypt on deployment
- **Database viewer** in development mode
- **Migration management UI**
- **One-command deployment** to multiple platforms
- **Built-in monitoring** and error tracking

---

**Status**: Specification Complete, Implementation Pending
**Priority**: High - Critical for improving new user experience
**Estimated Effort**: 2-3 days for Phase 1, 1 day each for Phases 2-3
