"""
Entrypoint script template for DNR Docker containers.

This module contains the Python script that runs inside Docker containers
to serve the DNR application. It's a self-contained FastAPI server that
loads pre-generated specs and provides CRUD endpoints.
"""

from __future__ import annotations

# The entrypoint script runs inside the Docker container.
# It's written to a file and executed by Python in the container.
DNR_ENTRYPOINT_TEMPLATE = '''#!/usr/bin/env python3
"""
DNR Docker Entrypoint - Self-contained runtime for Docker containers.

Loads pre-generated specs and runs a minimal FastAPI server.
"""

import json
import os
import asyncio
from pathlib import Path
from typing import Any

# FastAPI and Uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

import uvicorn

# Configuration from environment
API_PORT = int(os.environ.get("DNR_API_PORT", 8000))
FRONTEND_PORT = int(os.environ.get("DNR_FRONTEND_PORT", 3000))
HOST = os.environ.get("DNR_HOST", "0.0.0.0")
DB_PATH = os.environ.get("DNR_DB_PATH", "/app/.dazzle/data.db")
TEST_MODE = os.environ.get("DNR_TEST_MODE", "0") == "1"
AUTH_ENABLED = os.environ.get("DNR_AUTH_ENABLED", "0") == "1"
AUTH_DB_PATH = os.environ.get("DNR_AUTH_DB_PATH", "/app/.dazzle/auth.db")

# Load specs
with open("backend_spec.json") as f:
    BACKEND_SPEC = json.load(f)
with open("ui_spec.json") as f:
    UI_SPEC = json.load(f)

# In-memory data store (simple dict-based storage)
DATA_STORE: dict[str, dict[str, Any]] = {}


def get_entity_config(entity_name: str) -> dict | None:
    """Get entity configuration from backend spec."""
    for entity in BACKEND_SPEC.get("entities", []):
        if entity.get("name") == entity_name:
            return entity
    return None


def get_collection(entity_name: str) -> dict[str, Any]:
    """Get or create collection for entity."""
    if entity_name not in DATA_STORE:
        DATA_STORE[entity_name] = {}
    return DATA_STORE[entity_name]


# Create FastAPI app
app = FastAPI(
    title=BACKEND_SPEC.get("name", "DNR API"),
    description="Auto-generated API from Dazzle DSL",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "mode": "docker"}


@app.get("/api/ui-spec")
async def get_ui_spec():
    """Return the UI specification."""
    return UI_SPEC


# Dynamic entity CRUD endpoints
for entity in BACKEND_SPEC.get("entities", []):
    entity_name = entity["name"]
    route_prefix = f"/api/{entity_name.lower()}s"

    # Create closure to capture entity_name
    def make_crud_handlers(ename: str):
        async def list_items():
            collection = get_collection(ename)
            items = list(collection.values())
            return {"items": items, "total": len(items)}

        async def create_item(request: Request):
            import uuid
            data = await request.json()
            item_id = str(uuid.uuid4())
            data["id"] = item_id
            collection = get_collection(ename)
            collection[item_id] = data
            return data

        async def get_item(item_id: str):
            collection = get_collection(ename)
            if item_id not in collection:
                raise HTTPException(status_code=404, detail=f"{ename} not found")
            return collection[item_id]

        async def update_item(item_id: str, request: Request):
            collection = get_collection(ename)
            if item_id not in collection:
                raise HTTPException(status_code=404, detail=f"{ename} not found")
            data = await request.json()
            data["id"] = item_id
            collection[item_id].update(data)
            return collection[item_id]

        async def delete_item(item_id: str):
            collection = get_collection(ename)
            if item_id not in collection:
                raise HTTPException(status_code=404, detail=f"{ename} not found")
            del collection[item_id]
            return {"deleted": True}

        return list_items, create_item, get_item, update_item, delete_item

    list_h, create_h, get_h, update_h, delete_h = make_crud_handlers(entity_name)

    # Register routes
    app.get(route_prefix)(list_h)
    app.post(route_prefix)(create_h)
    app.get(f"{route_prefix}/{{item_id}}")(get_h)
    app.put(f"{route_prefix}/{{item_id}}")(update_h)
    app.delete(f"{route_prefix}/{{item_id}}")(delete_h)


# =============================================================================
# Authentication
# =============================================================================

# Auth data stores (simple in-memory for now)
AUTH_USERS: dict[str, dict] = {}
AUTH_SESSIONS: dict[str, dict] = {}


def hash_password_simple(password: str, salt: str | None = None) -> str:
    """Simple password hashing using hashlib."""
    import hashlib
    import secrets as _secrets
    if salt is None:
        salt = _secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"{salt}${key.hex()}"


def verify_password_simple(password: str, password_hash: str) -> bool:
    """Verify password against hash."""
    try:
        salt, _ = password_hash.split("$")
        return hash_password_simple(password, salt) == password_hash
    except ValueError:
        return False


if AUTH_ENABLED:
    import secrets as auth_secrets
    from datetime import UTC, datetime, timedelta
    from pydantic import BaseModel as PydanticBaseModel

    class LoginRequest(PydanticBaseModel):
        email: str
        password: str

    class RegisterRequest(PydanticBaseModel):
        email: str
        password: str
        display_name: str | None = None

    @app.post("/api/auth/register")
    async def auth_register(data: RegisterRequest):
        """Register a new user."""
        import uuid
        if data.email in AUTH_USERS:
            raise HTTPException(status_code=400, detail="Email already registered")

        user_id = str(uuid.uuid4())
        user = {
            "id": user_id,
            "email": data.email,
            "password_hash": hash_password_simple(data.password),
            "display_name": data.display_name or data.email.split("@")[0],
            "is_active": True,
            "created_at": datetime.now(UTC).isoformat(),
        }
        AUTH_USERS[data.email] = user

        # Create session
        session_token = auth_secrets.token_urlsafe(32)
        session = {
            "user_id": user_id,
            "token": session_token,
            "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        }
        AUTH_SESSIONS[session_token] = session

        response = JSONResponse({
            "user": {
                "id": user_id,
                "email": data.email,
                "display_name": user["display_name"],
            },
            "message": "Registration successful"
        }, status_code=201)
        response.set_cookie(
            "dnr_session", session_token,
            httponly=True, samesite="lax", max_age=7*24*60*60
        )
        return response

    @app.post("/api/auth/login")
    async def auth_login(data: LoginRequest):
        """Login with email and password."""
        import uuid
        user = AUTH_USERS.get(data.email)
        if not user or not verify_password_simple(data.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not user.get("is_active", True):
            raise HTTPException(status_code=401, detail="Account is disabled")

        # Create session
        session_token = auth_secrets.token_urlsafe(32)
        session = {
            "user_id": user["id"],
            "token": session_token,
            "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        }
        AUTH_SESSIONS[session_token] = session

        response = JSONResponse({
            "user": {
                "id": user["id"],
                "email": user["email"],
                "display_name": user.get("display_name"),
            },
            "message": "Login successful"
        })
        response.set_cookie(
            "dnr_session", session_token,
            httponly=True, samesite="lax", max_age=7*24*60*60
        )
        return response

    @app.post("/api/auth/logout")
    async def auth_logout(request: Request):
        """Logout and invalidate session."""
        session_token = request.cookies.get("dnr_session")
        if session_token and session_token in AUTH_SESSIONS:
            del AUTH_SESSIONS[session_token]

        response = JSONResponse({"message": "Logout successful"})
        response.delete_cookie("dnr_session")
        return response

    @app.get("/api/auth/me")
    async def auth_me(request: Request):
        """Get current user."""
        session_token = request.cookies.get("dnr_session")
        if not session_token or session_token not in AUTH_SESSIONS:
            raise HTTPException(status_code=401, detail="Not authenticated")

        session = AUTH_SESSIONS[session_token]
        # Check expiry
        if datetime.fromisoformat(session["expires_at"]) < datetime.now(UTC):
            del AUTH_SESSIONS[session_token]
            raise HTTPException(status_code=401, detail="Session expired")

        # Find user
        user = None
        for u in AUTH_USERS.values():
            if u["id"] == session["user_id"]:
                user = u
                break

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name"),
            "is_authenticated": True,
        }


# Test mode endpoints
if TEST_MODE:
    @app.post("/__test__/reset")
    async def test_reset():
        """Reset all data."""
        DATA_STORE.clear()
        if AUTH_ENABLED:
            AUTH_USERS.clear()
            AUTH_SESSIONS.clear()
        return {"reset": True}

    @app.post("/__test__/seed")
    async def test_seed(request: Request):
        """Seed data."""
        data = await request.json()
        for entity_name, items in data.items():
            collection = get_collection(entity_name)
            for item in items:
                if "id" not in item:
                    import uuid
                    item["id"] = str(uuid.uuid4())
                collection[item["id"]] = item
        return {"seeded": True}

    @app.get("/__test__/snapshot")
    async def test_snapshot():
        """Get database snapshot."""
        snapshot = dict(DATA_STORE)
        if AUTH_ENABLED:
            # Include user count (not full data for security)
            snapshot["__auth__"] = {
                "user_count": len(AUTH_USERS),
                "session_count": len(AUTH_SESSIONS),
            }
        return snapshot

    if AUTH_ENABLED:
        @app.post("/__test__/create_user")
        async def test_create_user(request: Request):
            """Create a test user with optional persona."""
            import uuid
            from datetime import UTC, datetime
            data = await request.json()

            email = data.get("email")
            password = data.get("password")
            display_name = data.get("display_name")
            persona = data.get("persona")

            if not email or not password:
                raise HTTPException(status_code=400, detail="email and password required")

            if email in AUTH_USERS:
                # Return existing user (idempotent)
                user = AUTH_USERS[email]
                return {
                    "id": user["id"],
                    "email": user["email"],
                    "display_name": user.get("display_name"),
                    "persona": user.get("persona"),
                    "created": False,
                }

            user_id = str(uuid.uuid4())
            user = {
                "id": user_id,
                "email": email,
                "password_hash": hash_password_simple(password),
                "display_name": display_name or email.split("@")[0],
                "persona": persona,
                "is_active": True,
                "created_at": datetime.now(UTC).isoformat(),
            }
            AUTH_USERS[email] = user

            return {
                "id": user_id,
                "email": email,
                "display_name": user["display_name"],
                "persona": persona,
                "created": True,
            }

        @app.post("/__test__/authenticate")
        async def test_authenticate(request: Request):
            """Authenticate for testing (creates session without password check)."""
            import uuid
            from datetime import UTC, datetime, timedelta
            import secrets as test_secrets

            data = await request.json()
            email = data.get("email") or data.get("username")
            role = data.get("role")

            # Find or create user
            if email not in AUTH_USERS:
                user_id = str(uuid.uuid4())
                user = {
                    "id": user_id,
                    "email": email,
                    "password_hash": hash_password_simple("test_password"),
                    "display_name": email.split("@")[0] if email else f"test_{role or 'user'}",
                    "persona": role,
                    "is_active": True,
                    "created_at": datetime.now(UTC).isoformat(),
                }
                AUTH_USERS[email] = user
            else:
                user = AUTH_USERS[email]

            # Create session
            session_token = test_secrets.token_urlsafe(32)
            session = {
                "user_id": user["id"],
                "token": session_token,
                "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            }
            AUTH_SESSIONS[session_token] = session

            response = JSONResponse({
                "user": {
                    "id": user["id"],
                    "email": user.get("email"),
                    "display_name": user.get("display_name"),
                    "persona": user.get("persona"),
                },
                "session_token": session_token,
            })
            response.set_cookie(
                "dnr_session", session_token,
                httponly=True, samesite="lax", max_age=7*24*60*60
            )
            return response

    # Provide mock authenticate endpoint when TEST_MODE is true but AUTH is disabled
    # This allows E2E tests to work with authenticated: true preconditions
    if not AUTH_ENABLED:
        @app.post("/__test__/authenticate")
        async def test_authenticate_mock(request: Request):
            """Mock authentication for testing (no real auth system)."""
            import uuid

            data = await request.json()
            username = data.get("username") or data.get("email")
            role = data.get("role")

            # Return a mock response similar to the local test_routes.py
            user_id = str(uuid.uuid4())
            username = username or f"test_{role or 'user'}"
            role = role or "user"
            session_token = str(uuid.uuid4())

            return {
                "user_id": user_id,
                "username": username,
                "role": role,
                "session_token": session_token,
            }


# =============================================================================
# Static Pages (privacy, terms, etc.)
# =============================================================================

# Simple markdown to HTML converter (no external dependencies)
def simple_markdown_to_html(text: str) -> str:
    """Convert basic markdown to HTML."""
    import re
    lines = text.split('\\n')
    html_lines = []
    in_list = False
    in_code = False

    for line in lines:
        # Code blocks
        if line.strip().startswith('```'):
            if in_code:
                html_lines.append('</pre></code>')
                in_code = False
            else:
                html_lines.append('<code><pre>')
                in_code = True
            continue
        if in_code:
            html_lines.append(line)
            continue

        # Headers
        if line.startswith('### '):
            html_lines.append(f'<h3>{line[4:]}</h3>')
        elif line.startswith('## '):
            html_lines.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith('# '):
            html_lines.append(f'<h1>{line[2:]}</h1>')
        # Unordered lists
        elif line.strip().startswith('- ') or line.strip().startswith('* '):
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            content = line.strip()[2:]
            html_lines.append(f'<li>{content}</li>')
        else:
            if in_list and line.strip() == '':
                html_lines.append('</ul>')
                in_list = False
            # Bold and italic
            line = re.sub(r'[*][*](.+?)[*][*]', r'<strong>\\1</strong>', line)
            line = re.sub(r'[*](.+?)[*]', r'<em>\\1</em>', line)
            # Links
            line = re.sub(r'\\[([^\\]]+)\\]\\(([^)]+)\\)', r'<a href="\\2">\\1</a>', line)
            # Paragraphs
            if line.strip():
                html_lines.append(f'<p>{line}</p>')
            else:
                html_lines.append('')

    if in_list:
        html_lines.append('</ul>')

    return '\\n'.join(html_lines)


# Get static pages from UI spec
def get_static_page(route: str) -> dict | None:
    """Find static page by route."""
    pages = UI_SPEC.get("shell", {}).get("pages", [])
    for page in pages:
        if page.get("route") == route:
            return page
    return None


@app.get("/api/pages/{path:path}")
async def serve_static_page(path: str):
    """Serve static page content."""
    route = f"/{path}"
    page = get_static_page(route)

    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Check if we have inline content
    content = page.get("content")
    if content:
        # Content is already HTML or markdown
        if not content.strip().startswith('<'):
            content = simple_markdown_to_html(content)
        return {"title": page.get("title", ""), "content": content}

    # Check for source file (in static/pages/)
    src = page.get("src")
    if src:
        # Try to find the source file
        page_file = Path("/app/static/pages") / Path(src).name
        if page_file.exists():
            file_content = page_file.read_text()
            # Convert markdown if needed
            if src.endswith('.md'):
                file_content = simple_markdown_to_html(file_content)
            return {"title": page.get("title", ""), "content": file_content}

    # Return placeholder content
    return {
        "title": page.get("title", "Page"),
        "content": f"<p>Content for {route} is not yet available.</p>"
    }


# Static files / UI serving
static_dir = Path("/app/static")
if static_dir.exists():
    @app.get("/", response_class=HTMLResponse)
    async def serve_ui():
        return (static_dir / "index.html").read_text()

    @app.get("/{path:path}")
    async def serve_static(path: str):
        file_path = static_dir / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        # SPA fallback
        return HTMLResponse((static_dir / "index.html").read_text())


if __name__ == "__main__":
    print(f"[DNR] Starting server on {HOST}:{API_PORT}")
    print(f"[DNR] Test mode: {TEST_MODE}")
    print(f"[DNR] Auth enabled: {AUTH_ENABLED}")
    print(f"[DNR] Entities: {[e['name'] for e in BACKEND_SPEC.get('entities', [])]}")
    uvicorn.run(app, host=HOST, port=API_PORT)
'''
