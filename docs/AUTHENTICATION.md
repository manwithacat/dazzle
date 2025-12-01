# DAZZLE Authentication Guide

**Version**: 1.0
**Last Updated**: 2025-12-01

This guide covers the built-in authentication system in DNR (Dazzle Native Runtime).

---

## Overview

DNR provides session-based authentication out of the box:

- **Session cookies**: HTTP-only cookies for security
- **SQLite storage**: Separate auth database (`.dazzle/auth.db`)
- **Password hashing**: PBKDF2-SHA256 with salt
- **Persona support**: Role-based access tied to DSL personas

---

## Quick Start

Authentication is automatically enabled when your DSL includes personas or auth-related entities.

```bash
# Run with auth enabled
dazzle dnr serve
```

**Default URLs**:
- Login: `POST /auth/login`
- Register: `POST /auth/register`
- Logout: `POST /auth/logout`
- Current user: `GET /auth/me`

---

## Table of Contents

1. [API Endpoints](#api-endpoints)
2. [DSL Integration](#dsl-integration)
3. [Personas & Roles](#personas--roles)
4. [Frontend Integration](#frontend-integration)
5. [Access Control](#access-control)
6. [Testing Auth Flows](#testing-auth-flows)
7. [Configuration](#configuration)

---

## API Endpoints

### Login

```http
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "secretpassword"
}
```

**Success Response** (200):
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "username": "username",
    "roles": ["user"]
  },
  "message": "Login successful"
}
```

Sets `dnr_session` cookie (HTTP-only, 7-day expiry).

**Error Response** (401):
```json
{
  "detail": "Invalid credentials"
}
```

### Register

```http
POST /auth/register
Content-Type: application/json

{
  "email": "newuser@example.com",
  "password": "secretpassword",
  "username": "optional_username"
}
```

**Success Response** (201):
```json
{
  "user": {
    "id": "uuid",
    "email": "newuser@example.com",
    "username": "optional_username",
    "roles": []
  },
  "message": "Registration successful"
}
```

Auto-logs in after registration.

**Error Response** (400):
```json
{
  "detail": "Email already registered"
}
```

### Logout

```http
POST /auth/logout
```

**Response** (200):
```json
{
  "message": "Logout successful"
}
```

Clears session cookie and invalidates server session.

### Get Current User

```http
GET /auth/me
```

**Success Response** (200):
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "username": "username",
  "roles": ["admin", "user"],
  "is_superuser": false
}
```

**Error Response** (401):
```json
{
  "detail": "Not authenticated"
}
```

### Change Password

```http
POST /auth/change-password
Content-Type: application/json

{
  "current_password": "oldpassword",
  "new_password": "newpassword"
}
```

**Success Response** (200):
```json
{
  "message": "Password changed successfully"
}
```

Invalidates all other sessions for security.

---

## DSL Integration

### Enabling Authentication

Authentication is auto-enabled when your DSL includes:

1. **Personas**:
```dsl
persona admin "Administrator":
  description: "System administrator"
  default_workspace: admin_dashboard

persona user "Regular User":
  description: "Standard user"
  default_workspace: user_home
```

2. **User entity with auth fields**:
```dsl
entity User "User":
  id: uuid pk
  email: email unique required
  password: str(200) required  # Triggers auth detection
  username: str(100)
  is_active: bool=true
  created_at: datetime auto_add
```

**Auth field detection**: Fields named `password`, `password_hash`, `email` trigger automatic auth setup.

### Persona Binding

Users are assigned personas through roles:

```dsl
persona agent "Support Agent":
  description: "Handles tickets"
  default_workspace: ticket_queue
```

A user with `roles: ["agent"]` maps to the `agent` persona.

---

## Personas & Roles

### Role Assignment

Assign roles when creating users (via API or test fixtures):

```json
{
  "email": "admin@example.com",
  "password": "adminpass",
  "roles": ["admin", "user"]
}
```

### Checking Roles

In protected routes, use role requirements:

```python
from dazzle_dnr_back.runtime.auth import create_auth_dependency

# Require admin role
require_admin = create_auth_dependency(
    auth_store,
    require_roles=["admin"]
)

@app.get("/admin-only")
async def admin_route(auth: AuthContext = Depends(require_admin)):
    return {"message": "Admin access granted"}
```

### Persona Resolution

The UI resolves persona from user roles:

```javascript
// User with roles: ["agent", "user"]
// Maps to persona: "agent" (first matching persona)
```

---

## Frontend Integration

### Auth Modal

DNR UI includes a built-in auth modal. Trigger it with:

```html
<button data-dazzle-auth-action="login">Sign In</button>
```

### Semantic Attributes

Auth-related attributes for E2E testing:

| Attribute | Element | Description |
|-----------|---------|-------------|
| `data-dazzle-auth-action="login"` | Button | Login trigger |
| `data-dazzle-auth-action="logout"` | Button | Logout trigger |
| `data-dazzle-auth-user="true"` | Container | User indicator |
| `data-dazzle-persona="admin"` | Container | Current persona |

### Standard Element IDs

DNR auth UI uses these IDs:

| ID | Element |
|----|---------|
| `#dz-auth-modal` | Modal container |
| `#dz-auth-form` | Login/register form |
| `#dz-auth-submit` | Submit button |
| `#dz-auth-error` | Error message |

### JavaScript Events

Listen for auth events:

```javascript
// Login success
window.addEventListener('dnr-auth-login', (e) => {
  console.log('User:', e.detail.user);
  // { id, email, display_name, persona }
});

// Logout
window.addEventListener('dnr-auth-logout', () => {
  console.log('User logged out');
});

// Auth error
window.addEventListener('dnr-auth-error', (e) => {
  console.log('Error:', e.detail.message);
});
```

---

## Access Control

### Route Protection

DNR supports declarative access control in the DSL (planned) and programmatic control:

```python
from dazzle_dnr_back.runtime.auth import (
    create_auth_dependency,
    create_optional_auth_dependency
)

# Required authentication
require_auth = create_auth_dependency(auth_store)

# Optional authentication (returns context even if not logged in)
optional_auth = create_optional_auth_dependency(auth_store)

# Role-based
require_admin = create_auth_dependency(
    auth_store,
    require_roles=["admin"]
)
```

### Access Policies

Entity access policies (in code):

```python
from dazzle_dnr_back.runtime.access_control import AccessPolicy

# Public access
AccessPolicy.create_public("Entity")

# Authenticated users only
AccessPolicy.create_authenticated("Entity")

# Owner only
AccessPolicy.create_owner("Entity", owner_field="user_id")
```

---

## Testing Auth Flows

### Enable Test Mode

```bash
dazzle dnr serve --test-mode
```

This enables test endpoints at `/__test__/`.

### Test Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/__test__/create_user` | POST | Create test user |
| `/__test__/authenticate` | POST | Create test session |
| `/__test__/reset` | POST | Reset auth database |

### E2E Test Fixtures

```json
{
  "fixtures": [
    {
      "id": "auth_test_user",
      "entity": "_User",
      "data": {
        "email": "test@example.com",
        "password": "testpass123",
        "display_name": "Test User",
        "persona": "user"
      }
    }
  ]
}
```

### Auth Flow Assertions

```json
{
  "steps": [
    {
      "kind": "click",
      "target": "auth:login_button"
    },
    {
      "kind": "fill",
      "target": "auth:field.email",
      "fixture_ref": "auth_test_user.email"
    },
    {
      "kind": "fill",
      "target": "auth:field.password",
      "fixture_ref": "auth_test_user.password"
    },
    {
      "kind": "click",
      "target": "auth:submit"
    },
    {
      "kind": "assert",
      "assertion": {
        "kind": "is_authenticated"
      }
    }
  ]
}
```

See [E2E_TESTING.md](E2E_TESTING.md) for complete auth testing documentation.

---

## Configuration

### Database Location

Auth uses a separate SQLite database:

```bash
# Default
.dazzle/auth.db

# Custom path
dazzle dnr serve --auth-db ./custom/auth.db
```

### Session Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Cookie name | `dnr_session` | Session cookie name |
| Expiry | 7 days | Session lifetime |
| HTTP-only | true | Cookie not accessible via JS |
| Secure | false | Set true for HTTPS |
| SameSite | lax | CSRF protection |

### Password Requirements

Default password hashing:
- Algorithm: PBKDF2-SHA256
- Iterations: 100,000
- Salt: 16-byte random

---

## Security Considerations

### Production Checklist

1. **Use HTTPS**: Set `secure=True` for cookies
2. **Strong passwords**: Enforce minimum length
3. **Rate limiting**: Add login attempt limits
4. **Audit logging**: Track auth events
5. **Session cleanup**: Periodically clear expired sessions

### Cookie Security

The `dnr_session` cookie is:
- **HTTP-only**: Not accessible via JavaScript
- **SameSite=Lax**: CSRF protection for most cases
- **Not secure by default**: Enable for HTTPS

### Password Storage

Passwords are never stored in plain text:
1. Generate random 16-byte salt
2. Hash with PBKDF2-SHA256 (100k iterations)
3. Store as `salt$hash`

---

## Troubleshooting

### "Not authenticated" errors

1. Check cookie is being sent
2. Verify session hasn't expired
3. Check auth database exists

```bash
# Check auth database
ls -la .dazzle/auth.db
```

### Session issues

```bash
# Reset auth database
rm .dazzle/auth.db
dazzle dnr serve  # Recreates on start
```

### CORS issues

If frontend and backend are on different origins:

```python
# In custom server setup
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,  # Required for cookies
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Related Documentation

- [CAPABILITIES.md](CAPABILITIES.md) - Feature overview
- [E2E_TESTING.md](E2E_TESTING.md) - Testing auth flows
- [SEMANTIC_DOM_CONTRACT.md](SEMANTIC_DOM_CONTRACT.md) - Auth element attributes
