# DAZZLE Capabilities Matrix

**Version**: 0.1.0
**Last Updated**: 2025-11-23
**Status**: Complete feature reference

This document provides a comprehensive overview of what DAZZLE can do, what each stack supports, and what's coming in future versions.

---

## Table of Contents

1. [DSL Constructs](#dsl-constructs)
2. [Stack Comparison](#stack-comparison)
3. [Feature Availability by Version](#feature-availability-by-version)
4. [What DAZZLE Can Do Today](#what-dazzle-can-do-today)
5. [What DAZZLE Cannot Do Yet](#what-dazzle-cannot-do-yet)
6. [Integration Features](#integration-features)

---

## DSL Constructs

### Entities ✅ Complete

**Status**: Fully implemented, production-ready
**Generates**: Database models, API endpoints, admin interfaces, forms

**Field Types Supported**:

| Field Type | Django | Express | OpenAPI | Description |
|------------|--------|---------|---------|-------------|
| `str(N)` | ✅ CharField | ✅ STRING | ✅ string | Variable-length string, max N chars |
| `text` | ✅ TextField | ✅ TEXT | ✅ string | Unlimited text |
| `int` | ✅ IntegerField | ✅ INTEGER | ✅ integer | 32-bit integer |
| `decimal(P,S)` | ✅ DecimalField | ✅ DECIMAL | ✅ number | Precision P, scale S |
| `bool` | ✅ BooleanField | ✅ BOOLEAN | ✅ boolean | True/false |
| `date` | ✅ DateField | ✅ DATEONLY | ✅ date | Date only |
| `datetime` | ✅ DateTimeField | ✅ DATE | ✅ date-time | Date and time |
| `uuid` | ✅ UUIDField | ✅ UUID | ✅ uuid | UUID v4 |
| `email` | ✅ EmailField | ✅ STRING + validator | ✅ email | Email validation |
| `enum[a,b,c]` | ✅ CharField(choices) | ✅ ENUM | ✅ enum | Enumerated values |
| `ref Entity` | ✅ ForeignKey | ✅ belongsTo | ✅ reference | Foreign key reference |

**Field Modifiers**:

| Modifier | Django | Express | OpenAPI | Description |
|----------|--------|---------|---------|-------------|
| `required` | ✅ null=False | ✅ allowNull=false | ✅ required | Must provide value |
| `pk` | ✅ primary_key=True | ✅ primaryKey | ✅ N/A | Primary key |
| `unique` | ✅ unique=True | ✅ unique | ✅ N/A | Unique constraint |
| `auto_add` | ✅ auto_now_add | ✅ defaultValue=NOW | ✅ readOnly | Auto-set on create |
| `auto_update` | ✅ auto_now | ✅ update hook | ✅ readOnly | Auto-update on save |
| `=defaultValue` | ✅ default | ✅ defaultValue | ✅ default | Default value |

**Advanced Features**:

| Feature | Django | Express | OpenAPI | Notes |
|---------|--------|---------|---------|-------|
| Indexes | ✅ | ✅ | ❌ | Performance optimization |
| Unique constraints | ✅ | ✅ | ❌ | Multi-field uniqueness |
| Check constraints | ✅ | ⚠️ | ❌ | Django only |
| Cascade delete | ✅ | ✅ | ❌ | Foreign key behavior |

**Example**:
```dsl
entity User "User Account":
  id: uuid pk
  email: email required unique
  username: str(50) required unique
  full_name: str(200) required
  is_active: bool=true
  role: enum[admin,user,guest]=user
  created_at: datetime auto_add
  updated_at: datetime auto_update

  unique: email, username
  index: created_at desc
```

**Generates**:
- **Django**: `models.py` with User model, migrations, admin interface
- **Express**: Sequelize model with validators, associations
- **OpenAPI**: User schema with all validations

---

### Surfaces ✅ Complete

**Status**: Fully implemented, production-ready
**Generates**: Forms, views, templates, API endpoints, UI components

**Surface Modes**:

| Mode | Django | Express | OpenAPI | Description |
|------|--------|---------|---------|-------------|
| `view` | ✅ DetailView | ✅ Detail page | ✅ GET /entity/{id} | Read-only detail |
| `create` | ✅ CreateView + Form | ✅ Create page | ✅ POST /entity | Create new entity |
| `edit` | ✅ UpdateView + Form | ✅ Edit page | ✅ PUT/PATCH /entity/{id} | Update existing |
| `list` | ✅ ListView | ✅ List page | ✅ GET /entity | List all entities |
| `custom` | ✅ FormView | ✅ Custom page | ✅ Custom endpoint | Custom logic |

**Field Display Options**:

| Option | Django | Express | Description |
|--------|--------|---------|-------------|
| Label | ✅ | ✅ | Custom field label |
| Help text | ✅ | ✅ | Explanatory text |
| Placeholder | ✅ | ✅ | Input placeholder |
| Read-only | ✅ | ✅ | Display only, no edit |
| Hidden | ✅ | ✅ | Hidden from form |

**Actions**:

| Outcome Type | Django | Express | OpenAPI | Description |
|--------------|--------|---------|---------|-------------|
| `surface` | ✅ Redirect | ✅ Redirect | ✅ Link | Navigate to surface |
| `experience` | ✅ Start flow | ✅ Start flow | ✅ Link | Begin experience |
| `integration` | ✅ Call API | ✅ Call API | ✅ Endpoint | Trigger integration |

**Example**:
```dsl
surface user_create "Create User":
  uses entity User
  mode: create

  section account_info "Account Information":
    field email "Email Address"
      placeholder: "user@example.com"
    field username "Username"
      help: "Letters, numbers, and underscores only"
    field password "Password"
      help: "Minimum 8 characters"

  section profile "Profile":
    field full_name "Full Name"
    field role "Account Type"

  action save "Create Account":
    outcome: surface user_detail
```

**Generates**:
- **Django**: CreateView, ModelForm, template with Bootstrap styling
- **Express**: Create route, EJS template, form validation
- **OpenAPI**: POST endpoint with request/response schemas

---

### Experiences ✅ Complete

**Status**: Fully implemented, production-ready
**Generates**: Multi-step workflows, state machines, flow orchestration

**Step Types**:

| Step Kind | Django | Express | Description |
|-----------|--------|---------|-------------|
| `surface` | ✅ | ✅ | Show a surface/form |
| `integration` | ✅ | ✅ | Call external API |
| `process` | ⚠️ | ⚠️ | Backend processing (limited) |

**Transitions**:

| Transition | Supported | Description |
|------------|-----------|-------------|
| `success →` | ✅ | Next step on success |
| `failure →` | ✅ | Next step on failure |
| `cancel →` | ✅ | Next step on cancel |
| Conditional | ⚠️ | Limited (simple conditions) |

**Example**:
```dsl
experience user_onboarding "User Onboarding Flow":
  start: create_account

  step create_account:
    kind: surface
    surface: user_create
    success → verify_email
    cancel → welcome_page

  step verify_email:
    kind: integration
    integration: email_verification
    success → complete_profile
    failure → create_account

  step complete_profile:
    kind: surface
    surface: profile_edit
    success → onboarding_complete
```

**Generates**:
- **Django**: Session-based flow with step tracking, redirects
- **Express**: Multi-page flow with state management
- **OpenAPI**: Flow documentation with step sequences

**Analysis**:
- ✅ Cycle detection
- ✅ Unreachable step detection
- ✅ Flow visualization (via inspect command)

---

### Services ✅ Complete

**Status**: Fully implemented, production-ready
**Defines**: External API configurations, authentication profiles

**Auth Profiles**:

| Auth Type | Supported | Description |
|-----------|-----------|-------------|
| `api_key_header` | ✅ | API key in header |
| `api_key_query` | ✅ | API key in query param |
| `oauth2_pkce` | ✅ | OAuth 2.0 with PKCE |
| `basic_auth` | ✅ | HTTP Basic Auth |
| `bearer_token` | ✅ | Bearer token |
| `custom` | ✅ | Custom headers |

**Example**:
```dsl
service stripe_api "Stripe Payments":
  spec: "https://api.stripe.com/v1"
  auth:
    kind: api_key_header
    header: "Authorization"
    prefix: "Bearer"
  owner: "payments-team"
```

**Generates**:
- **Django**: Service client configuration, auth middleware
- **Express**: Axios client with interceptors
- **OpenAPI**: External service documentation
- **Terraform**: API Gateway configuration (if applicable)

---

### Foreign Models ✅ Complete

**Status**: Fully implemented, production-ready
**Defines**: External data shapes from third-party services

**Constraints**:

| Constraint | Meaning |
|------------|---------|
| `read_only` | Cannot modify via this app |
| `event_driven` | Updates via webhooks/events |
| `batch_import` | Periodic bulk imports |

**Example**:
```dsl
foreign_model StripeCustomer "Stripe Customer":
  from service stripe_api
  key: customer_id

  id: str(100) required
  email: email required
  name: str(200)
  created: int required

  constraint: read_only
  constraint: event_driven
```

**Generates**:
- **Django**: Read-only model proxy, serializers
- **Express**: DTO (Data Transfer Object) classes
- **OpenAPI**: External schema definitions

---

### Integrations ⚠️ Partially Complete

**Status**: Functional with stubs (full implementation in v0.2)
**Defines**: Connections between app and external services

**Actions** (⚠️ Limited):
```dsl
integration stripe_checkout:
  uses service stripe_api
  uses foreign StripeCustomer

  action create_checkout:
    when surface payment_form
    call service stripe_api
    call operation /checkout/sessions
    call mapping:
      amount → form.total
      currency → form.currency
    response foreign StripeSession
    response entity Payment
    response mapping:
      session_id → entity.stripe_session_id
```

**Current State**:
- ✅ Parses action blocks
- ⚠️ Creates stub action (functional but placeholder mappings)
- ❌ Full mapping extraction (v0.2)

**Syncs** (⚠️ Limited):
```dsl
  sync import_customers:
    mode: scheduled "0 2 * * *"
    from service stripe_api
    from operation /customers
    from foreign StripeCustomer
    into entity Customer
    match rules:
      stripe_id ↔ id
      email ↔ email
```

**Current State**:
- ✅ Parses sync blocks
- ⚠️ Creates stub sync (functional but placeholder mappings)
- ❌ Full schedule and mapping extraction (v0.2)

**Generates**:
- **Django**: Celery tasks (scheduled), API clients
- **Express**: Node-cron jobs, service integrations
- **Terraform**: Lambda functions (if applicable)

---

### Tests ✅ Complete

**Status**: Fully implemented, generates test scaffolding
**Generates**: Unit tests, integration tests, fixtures

**Test Types**:

| Test Type | Django | Express | Description |
|-----------|--------|---------|-------------|
| Model tests | ✅ | ✅ | Entity validation, constraints |
| Form tests | ✅ | ✅ | Surface validation |
| View tests | ✅ | ✅ | Endpoint testing |
| Integration tests | ✅ | ✅ | End-to-end flows |

**Example**:
```dsl
test user_creation:
  entity: User
  test: create
  data:
    email: "test@example.com"
    username: "testuser"
    full_name: "Test User"
  expect: success

test duplicate_email:
  entity: User
  test: create
  data:
    email: "test@example.com"
  expect: failure "Email already exists"
```

**Generates**:
- **Django**: pytest-django tests with fixtures
- **Express**: Jest/Mocha tests with supertest
- **OpenAPI**: Schemathesis validation tests

---

## Stack Comparison

### Django Micro Modular ✅

**Best For**: Rapid prototyping, MVPs, internal tools, admin-heavy apps
**Setup Time**: 5 minutes to running app
**Deployment**: Heroku, Railway, PythonAnywhere, AWS Elastic Beanstalk

**What You Get**:
- ✅ **Models**: Django models with migrations (entities → models.py)
- ✅ **Admin**: Auto-configured Django admin (all entities)
- ✅ **Forms**: ModelForms with validation (surfaces → forms.py)
- ✅ **Views**: Class-based views (CreateView, UpdateView, DetailView, ListView)
- ✅ **Templates**: Bootstrap 5 styled templates (professional UI)
- ✅ **URLs**: Automatic routing (urls.py)
- ✅ **Settings**: Production-ready settings.py
- ✅ **Static files**: CSS, JavaScript bundled
- ✅ **Tests**: pytest-django test suite
- ✅ **Database**: SQLite (dev), PostgreSQL-ready (prod)
- ✅ **Post-build hooks**: Migrations, superuser creation

**Stack Capabilities**:

| Feature | Support | Notes |
|---------|---------|-------|
| CRUD operations | ✅ Full | All entity operations |
| Relationships | ✅ Full | ForeignKey, ManyToMany |
| Authentication | ✅ Django Auth | Built-in user model |
| Admin interface | ✅ Full | Auto-configured |
| Forms | ✅ Full | ModelForms with validation |
| Templates | ✅ Full | Bootstrap 5 |
| Experiences | ✅ Basic | Session-based flows |
| Integrations | ⚠️ Stubs | Celery tasks generated |
| Tests | ✅ Full | pytest-django |

**Example Output**:
```
my_app/
├── manage.py
├── my_app/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── tasks/
│   ├── models.py          # Task entity
│   ├── forms.py           # TaskForm
│   ├── views.py           # TaskListView, TaskCreateView, etc.
│   ├── admin.py           # TaskAdmin
│   ├── urls.py            # URL patterns
│   └── templates/tasks/   # task_list.html, task_detail.html, etc.
├── templates/base.html
├── static/
├── requirements.txt
└── README.md
```

---

### Django API ✅

**Best For**: RESTful APIs, mobile backends, SPA backends
**Setup Time**: 5 minutes
**Deployment**: Same as Django Micro + API gateways

**What You Get**:
- ✅ **Django REST Framework**: Full DRF setup
- ✅ **Serializers**: ModelSerializers (entities → serializers.py)
- ✅ **ViewSets**: CRUD endpoints (ModelViewSet)
- ✅ **Routers**: Automatic URL routing
- ✅ **OpenAPI**: Integrated schema generation (drf-spectacular)
- ✅ **Authentication**: Token auth, JWT-ready
- ✅ **CORS**: Configured for frontend apps
- ✅ **Filtering**: django-filter integration
- ✅ **Pagination**: Configurable pagination
- ✅ **Tests**: API test suite with APIClient

**Endpoints Generated**:

| Entity | Endpoints |
|--------|-----------|
| Task | GET /api/tasks/ (list) |
|      | POST /api/tasks/ (create) |
|      | GET /api/tasks/{id}/ (retrieve) |
|      | PUT /api/tasks/{id}/ (update) |
|      | PATCH /api/tasks/{id}/ (partial update) |
|      | DELETE /api/tasks/{id}/ (delete) |

**Example Output**:
```
my_api/
├── my_api/
│   ├── settings.py        # DRF configured
│   └── urls.py            # API router
├── tasks/
│   ├── models.py
│   ├── serializers.py     # TaskSerializer
│   ├── viewsets.py        # TaskViewSet
│   └── tests.py
├── api/
│   └── urls.py            # /api/ routing
└── requirements.txt       # DRF, drf-spectacular, etc.
```

---

### Express Micro ✅

**Best For**: Node.js developers, JavaScript stack consistency
**Setup Time**: 5 minutes
**Deployment**: Heroku, Vercel, Railway, AWS Lambda

**What You Get**:
- ✅ **Express.js**: Fast Node.js framework
- ✅ **Sequelize ORM**: Models with migrations (entities → models/)
- ✅ **EJS Templates**: Server-side rendering (surfaces → views/)
- ✅ **AdminJS**: Auto-generated admin panel
- ✅ **Routing**: Express Router (organized routes)
- ✅ **Validation**: express-validator
- ✅ **Session management**: express-session
- ✅ **SQLite**: Development database
- ✅ **Tests**: Jest test suite
- ✅ **npm scripts**: Build, dev, test commands

**Example Output**:
```
my-app/
├── server.js
├── config/
│   └── database.js        # Sequelize config
├── models/
│   └── Task.js            # Sequelize model
├── routes/
│   └── tasks.js           # Express routes
├── views/
│   ├── layout.ejs
│   └── tasks/             # task_list.ejs, task_form.ejs, etc.
├── public/
├── tests/
├── package.json
└── README.md
```

---

### OpenAPI ✅

**Best For**: API documentation, API-first design, code generation
**Setup Time**: 1 minute
**Consumers**: Swagger UI, Redoc, code generators (OpenAPI Generator)

**What You Get**:
- ✅ **OpenAPI 3.0**: Complete specification
- ✅ **Schemas**: All entities as schemas
- ✅ **Paths**: All surfaces as endpoints
- ✅ **Parameters**: Query, path, header params
- ✅ **Responses**: Success and error responses
- ✅ **Examples**: Request/response examples
- ✅ **Tags**: Organized by entity
- ✅ **Security**: Auth schemes (basic implementation)
- ✅ **Validation**: Schemathesis tests

**Example Output**:
```yaml
openapi: 3.0.0
info:
  title: My App API
  version: 0.1.0
paths:
  /tasks:
    get:
      summary: List tasks
      operationId: listTasks
      tags: [tasks]
      responses:
        '200':
          description: Success
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Task'
    post:
      summary: Create task
      # ... full CRUD operations
components:
  schemas:
    Task:
      type: object
      required: [title]
      properties:
        id:
          type: string
          format: uuid
        title:
          type: string
          maxLength: 200
        # ... all fields
```

**Usage**:
- View in Swagger UI
- Generate client SDKs (Python, TypeScript, Java, etc.)
- Import into Postman/Insomnia
- API contract testing

---

### Docker ✅

**Best For**: Local development, consistent environments, containerization
**Setup Time**: 2 minutes (+ image pull time)
**Deployment**: Any container platform (Docker Compose, Kubernetes, ECS)

**What You Get**:
- ✅ **docker-compose.yml**: Multi-service orchestration
- ✅ **Dockerfile**: Application container
- ✅ **Database service**: PostgreSQL/MySQL container
- ✅ **Environment vars**: Configuration management
- ✅ **Health checks**: Service monitoring
- ✅ **Networks**: Service isolation
- ✅ **Volumes**: Data persistence
- ✅ **Build hooks**: Database init, migrations

**Example Output**:
```yaml
version: '3.8'
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/myapp
    depends_on:
      - db
    volumes:
      - .:/app

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=myapp
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

**Commands**:
```bash
docker-compose up -d       # Start services
docker-compose logs -f     # View logs
docker-compose exec web python manage.py migrate
docker-compose down        # Stop services
```

---

### Terraform ✅

**Best For**: Infrastructure as code, AWS deployments, multi-environment setups
**Setup Time**: 5 minutes (+ deployment time)
**Deployment**: AWS (ECS, RDS, VPC, ALB)

**What You Get**:
- ✅ **main.tf**: Infrastructure definition
- ✅ **variables.tf**: Configurable parameters
- ✅ **outputs.tf**: Resource outputs
- ✅ **ECS**: Container orchestration (Fargate)
- ✅ **RDS**: Managed database (PostgreSQL/MySQL)
- ✅ **VPC**: Network isolation
- ✅ **ALB**: Load balancing
- ✅ **Security groups**: Firewall rules
- ✅ **IAM roles**: Permission management
- ✅ **Multi-environment**: dev/staging/prod

**Example Output**:
```
terraform/
├── main.tf                # Core infrastructure
├── variables.tf           # Input variables
├── outputs.tf             # Output values
├── ecs.tf                 # ECS cluster, tasks, services
├── rds.tf                 # Database
├── vpc.tf                 # Networking
├── alb.tf                 # Load balancer
├── security_groups.tf     # Firewall
└── iam.tf                 # Permissions
```

**Commands**:
```bash
terraform init             # Initialize
terraform plan             # Preview changes
terraform apply            # Deploy
terraform destroy          # Tear down
```

**Resources Created**:
- VPC with public/private subnets
- ECS cluster with Fargate tasks
- RDS PostgreSQL instance
- Application Load Balancer
- Auto-scaling groups
- CloudWatch logging
- Security groups and IAM roles

---

## Feature Availability by Version

| Feature | v0.1.0 | v0.2.0 | v2.0.0 | Notes |
|---------|--------|--------|--------|-------|
| **Core DSL** |
| Entity definition | ✅ | ✅ | ✅ | Complete |
| Surface definition | ✅ | ✅ | ✅ | Complete |
| Experience definition | ✅ | ✅ | ✅ | Complete |
| Service definition | ✅ | ✅ | ✅ | Complete |
| Foreign model definition | ✅ | ✅ | ✅ | Complete |
| Integration definition | ⚠️ | ✅ | ✅ | Stubs in v0.1 |
| Test definition | ✅ | ✅ | ✅ | Complete |
| **Module System** |
| Module declarations | ✅ | ✅ | ✅ | Complete |
| Use declarations | ✅ | ✅ | ✅ | Complete |
| Use validation (strict) | ✅ | ✅ | ✅ | NEW in v0.1 |
| Export declarations | ❌ | ❌ | ✅ | v2.0 |
| **Validation** |
| Type checking | ✅ | ✅ | ✅ | Complete |
| Reference validation | ✅ | ✅ | ✅ | Complete |
| Constraint validation | ✅ | ✅ | ✅ | Complete |
| Pattern detection | ✅ | ✅ | ✅ | NEW in v0.1 |
| Flow analysis | ✅ | ✅ | ✅ | NEW in v0.1 |
| **Stacks** |
| Django Micro Modular | ✅ | ✅ | ✅ | Complete |
| Django API | ✅ | ✅ | ✅ | Complete |
| Express Micro | ✅ | ✅ | ✅ | Complete |
| OpenAPI | ✅ | ✅ | ✅ | Complete |
| Docker | ✅ | ✅ | ✅ | Complete |
| Terraform | ✅ | ✅ | ✅ | Complete |
| Next.js | ❌ | ⚠️ | ✅ | Planned v0.2 |
| FastAPI | ❌ | ⚠️ | ✅ | Planned v0.2 |
| Vue | ❌ | ❌ | ⚠️ | Future |
| **LLM Integration** |
| Spec analysis | ✅ | ✅ | ✅ | Complete |
| DSL generation | ✅ | ✅ | ✅ | Complete |
| Interactive Q&A | ✅ | ✅ | ✅ | Complete |
| Multi-provider | ✅ | ✅ | ✅ | Anthropic, OpenAI |
| **IDE Integration** |
| LSP server | ✅ | ✅ | ✅ | Complete |
| VS Code extension | ✅ | ✅ | ✅ | Complete |
| Diagnostics | ✅ | ✅ | ✅ | Complete |
| Hover info | ✅ | ✅ | ✅ | Complete |
| Go-to-definition | ✅ | ✅ | ✅ | Complete |
| Auto-completion | ✅ | ✅ | ✅ | Complete |
| **CLI** |
| init, validate, build | ✅ | ✅ | ✅ | Complete |
| lint (extended) | ✅ | ✅ | ✅ | Complete |
| inspect | ✅ | ✅ | ✅ | NEW in v0.1 |
| analyze-spec | ✅ | ✅ | ✅ | Complete |
| --version flag | ❌ | ✅ | ✅ | Planned v0.2 |
| **Advanced** |
| Integration full parsing | ❌ | ✅ | ✅ | v0.2 |
| Port-based composition | ❌ | ❌ | ✅ | v2.0 |
| Formal verification | ❌ | ❌ | ✅ | v2.0 |
| Type catalog | ✅ | ✅ | ✅ | NEW in v0.1 |

**Legend**:
- ✅ Fully implemented
- ⚠️ Partial (functional but limited)
- ❌ Not implemented

---

## What DAZZLE Can Do Today

### Generate Production-Ready Applications

**In 5 Minutes**:
1. Write DSL defining entities and surfaces
2. Run `dazzle validate`
3. Run `dazzle build --stack micro`
4. Get working Django/Express app with:
   - Database models
   - Admin interface
   - Forms and views
   - Professional UI
   - Tests

### Support Complete Development Workflows

- **Design**: Use LLM to generate DSL from requirements
- **Validate**: Check DSL for errors before building
- **Build**: Generate code for multiple stacks simultaneously
- **Test**: Generated test suites ready to run
- **Deploy**: Docker and Terraform configs included
- **Document**: OpenAPI specs for API documentation

### Multi-Stack Flexibility

Same DSL generates:
- Django web app
- Django REST API
- Express.js app
- OpenAPI specification
- Docker containers
- AWS infrastructure

### Real-World Features

- ✅ **CRUD operations**: Full create, read, update, delete
- ✅ **Relationships**: Foreign keys, one-to-many, many-to-many
- ✅ **Validation**: Type checking, constraints, business rules
- ✅ **Authentication**: Built-in user models and auth
- ✅ **Admin interfaces**: Auto-generated admin panels
- ✅ **Workflows**: Multi-step experiences and flows
- ✅ **External APIs**: Service integrations (basic)
- ✅ **Testing**: Unit and integration tests
- ✅ **Deployment**: Container and cloud configurations

### Development Experience

- ✅ **IDE integration**: VS Code extension with real-time validation
- ✅ **Error messages**: Clear, actionable error reporting
- ✅ **Pattern detection**: Identifies incomplete CRUD, flow issues
- ✅ **Module system**: Organize large projects across files
- ✅ **Documentation**: Comprehensive reference docs
- ✅ **Examples**: Working example projects

---

## What DAZZLE Cannot Do Yet

### Limitations in v0.1.0

**Integration Parsing**:
- ⚠️ Action and sync blocks parse but use stubs
- ⚠️ Mapping rules not fully extracted
- ⚠️ Schedule expressions not parsed
- **Workaround**: Manually modify generated integration code

**OpenAPI Security**:
- ⚠️ Security schemes are placeholders
- **Workaround**: Manually add securitySchemes to OpenAPI spec

**Complex Workflows**:
- ❌ Conditional transitions (if/else logic)
- ❌ Parallel steps
- ❌ Loop constructs
- **Workaround**: Chain multiple experiences, customize generated code

**Advanced Validation**:
- ❌ Custom validators
- ❌ Cross-field validation (beyond unique constraints)
- ❌ Business rule expressions
- **Workaround**: Add validators to generated code

**Real-Time Features**:
- ❌ WebSocket support
- ❌ Real-time sync
- ❌ Event streaming
- **Workaround**: Add WebSocket support to generated code

### Not Supported (Design Limitations)

**UI Frameworks**:
- ❌ React/Vue components (only Django/Express templates)
- **Future**: Next.js, Vue stacks in v0.2

**Databases**:
- ❌ NoSQL databases (MongoDB, DynamoDB)
- Only: PostgreSQL, MySQL, SQLite
- **Future**: May add NoSQL support

**Microservices**:
- ❌ Service mesh, distributed tracing
- ❌ Event sourcing, CQRS patterns
- **Future**: v2.0 port-based composition

**Multi-Tenancy**:
- ❌ Tenant isolation
- ❌ Per-tenant databases
- **Workaround**: Customize generated code

---

## Integration Features

### LLM Integration ✅

**Capabilities**:
- Analyze natural language requirements
- Generate DSL from specifications
- Interactive Q&A for clarifications
- Cost estimation before generation
- Safety checks (no sensitive data)

**Supported Providers**:
- Anthropic Claude (3.5 Sonnet, Opus)
- OpenAI GPT (4, 4-turbo)

**Usage**:
```bash
dazzle analyze-spec requirements.md
dazzle analyze-spec requirements.md --generate-dsl
```

### LSP & IDE Support ✅

**Features**:
- Real-time syntax checking
- Error highlighting as you type
- Hover documentation
- Go-to-definition (entities, surfaces, etc.)
- Auto-completion
- Signature help

**Supported Editors**:
- VS Code (full extension)
- Neovim (via LSP)
- Emacs (via LSP)
- Any LSP-compatible editor

### Testing Support ✅

**Generated Tests**:
- Model/entity tests
- Form/serializer tests
- View/route tests
- Integration tests
- Fixtures and factories

**Test Frameworks**:
- pytest (Django)
- pytest-django (Django)
- Jest (Express)
- Schemathesis (OpenAPI validation)

### CI/CD Support ✅

**GitHub Actions**:
- Automated testing
- Build validation
- Multi-Python version matrix
- Coverage reporting

**Deployment Targets**:
- Heroku (Django, Express)
- Railway (Django, Express)
- AWS (via Terraform)
- Docker Compose (any platform)
- Vercel (Express)

---

## Summary

**What Works Great** ✅:
- Entity modeling with relationships
- CRUD surface generation
- Basic workflow experiences
- Multiple stack targets
- IDE integration
- LLM-assisted spec writing

**What Needs Work** ⚠️:
- Integration action/sync parsing (v0.2)
- Complex workflow logic (v0.2)
- OpenAPI security details (v0.2)

**What's Coming** 🔮:
- Full integration support (v0.2)
- More stacks: Next.js, FastAPI (v0.2)
- Export declarations (v2.0)
- Port-based composition (v2.0)
- Formal verification (v2.0)

---

**For Questions**: See docs/DAZZLE_DSL_REFERENCE_0_1.md for complete syntax reference.
**For Examples**: Check examples/ directory for working projects.
**For Help**: Open an issue at https://github.com/manwithacat/dazzle/issues
