---
hide:
  - navigation
---

# Asyncz Dashboard & Admin

This page explains what the Asyncz dashboard is, why you might want it, and exactly how to add it to your
ASGI application, with or without login, plus how to extend the auth backend to your needs.

This admin is built on top of [Lilya](https://lilya.dev) but since its ASGI, you can integrate with your favourite
framework like Ravyn, FastAPI, Litestar, Starlette.

We use Lilya in our examples since it was built on top of it but feel free to apply this to your favourite framework.

## What is it?

The **Asyncz Dashboard** is a web UI (and tiny management API) for inspecting and controlling an `AsyncIOScheduler` from the browser.
It ships with:

- A clean, responsive UI (Tailwind + HTMX).
- A tasks table with run/pause/resume/remove and bulk actions.
- Drop-in admin wrapper (`AsynczAdmin`) that can optionally protect the dashboard with login.
- A simple, pluggable auth system so you can bring your own auth (session, headers, JWT, etc).

The dashboard lives in `asyncz.contrib.dashboard` and the admin wrapper lives in `asyncz.contrib.dashboard.admin`.

!!! Note "Very Important"
    You can implement your own AuthBackend but at the moment the AuthGateMiddleware is using sessions until further versions
    of the admin will come out. For now it will be limited to sessions.

## Why use it?

- **Visibility.** See all scheduled tasks, next run times, and states at a glance.
- **Control.** Trigger, pause, resume, and delete without touching code.
- **Safety.** Optional login gate so only authorized users can access it.
- **Pluggable auth.** Use our simple username/password backend or hook into your own user system.
- **Embeddable.** Mount it as a child app anywhere in your existing Lilya project.

## Installation

Install the dashboard extra:

```bash
pip install asyncz[dashboard]
```

This pulls in the dashboard templates/assets and minimal dependencies needed for the UI. It will automatically install
the remaining dependencies required to make the dashboard shine.

## Configuration (settings)

Asyncz exposes [settings](./settings.md) similar to Lilya.
Defaults are provided by `asyncz.conf.global_settings.Settings`, and you can override them via the environment
variable `ASYNCZ_SETTINGS_MODULE`.

### Default access

```python
from asyncz import settings

# dashboard_config is a property that returns DashboardConfig
config = settings.dashboard_config

# e.g.
prefix = config.dashboard_url_prefix        # default UI mount prefix
session_middleware = config.session_middleware      # session middleware definition
```

### Override settings (your own settings module)

Create a module, e.g. `myproject.asyncz_settings`:

```python
# myproject/asyncz_settings.py
from typing import Any
from asyncz.conf.global_settings import Settings as BaseSettings

class Settings(BaseSettings):
    # You can add overrides or utility properties here.
    # Example: if your DashboardConfig reads from these:
    # debug: bool = True
    @property
    def dashboard_config(self) -> Any:
        """
        Retrieves the default configuration settings for the Asyncz management dashboard.

        This property dynamically imports and returns an instance of the `DashboardConfig`
        class, providing access to settings like the authentication backend, template
        directory, and static files location.

        Returns:
            An instance of `DashboardConfig`.
        """
        from asyncz.contrib.dashboard.config import DashboardConfig

        return DashboardConfig()
```

Point Asyncz to it:

```bash
export ASYNCZ_SETTINGS_MODULE="myproject.asyncz_settings.Settings"
```

Anywhere in your code you can import:

```python
from asyncz import settings
```

The dashboard itself reads its config via `settings.dashboard_config`,
which should return an instance of `asyncz.contrib.dashboard.config.DashboardConfig` (the default implementation).

You can customize your `DashboardConfig` to change `dashboard_url_prefix`, `session_middleware`, template locations, etc.

### The DashboardConfig

This is where you can change custom dashboard settings to match your preferences.

```python
# myproject/dashboard/config.py
from asyncz.contrib.dashboard.config import DashboardConfig


class MyDashboard(DashboardConfig):
    title: str = "Dashboard"
    header_title: str = "Asyncz "
    description: str = "A simple dashboard for monitoring Asyncz tasks."
    dashboard_url_prefix: str = "/my-dashboard"
    sidebar_bg_colour: str = "#f06824"
```

Now you can override this in your custom settings.

```python
from typing import Any
from asyncz.conf.global_settings import Settings as BaseSettings

class Settings(BaseSettings):
    # You can add overrides or utility properties here.
    # Example: if your DashboardConfig reads from these:
    # debug: bool = True
    @property
    def dashboard_config(self) -> Any:
        from myproject.dashboard.config import MyDashboard

        return MyDashboard()
```

And this is it, your dashboard now uses your custom settings instead of the default ones.

## `AsynczAdmin`: the dashboard wrapper

`AsynczAdmin` builds a private `Lilya` object but any Lilya object is an **ASGI** app containing the dashboard (and optional login/logout).
You mount it into your existing application at a URL prefix.

### If you are using Lilya

There is a method that does this automatically for you and **only works with Lilya applications.**

```python
from lilya.apps import Lilya
from asyncz.contrib.dashboard.admin import AsynczAdmin
from asyncz.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(stores={"default": {"type": "memory"}})

app = Lilya()

admin = AsynczAdmin(
    enable_login=False,             # or True to require auth
    backend=None,                   # required if enable_login=True
    url_prefix="/dashboard",        # default comes from settings.dashboard_config
    scheduler=scheduler,            # pass your scheduler or let it create a default one
    include_session=True,           # include session middleware from config
    include_cors=True,              # include permissive CORS
    login_path="/login",            # where your login view lives within the child app
    allowlist=("/login", "/logout", "/static", "/assets"),  # paths bypassing auth gate
)

# This only works for Lilya
admin.include_in(app)

@app.on_event("startup")
async def start():
    scheduler.start()

@app.on_event("shutdown")
async def stop():
    scheduler.shutdown()
```

### If you are using something else

Each framework has its own way of including ASGI applications so you must follow the guidelines of the framework and use
the `get_asgi_app()` function from the admin to mount.

Let us see an example using Starlette.

```python
from starlette.applications import Starlette
from starlette.routing import Mount
from asyncz.contrib.dashboard.admin import AsynczAdmin
from asyncz.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(stores={"default": {"type": "memory"}})

admin = AsynczAdmin(
    enable_login=False,             # or True to require auth
    backend=None,                   # required if enable_login=True
    url_prefix="/dashboard",        # default comes from settings.dashboard_config
    scheduler=scheduler,            # pass your scheduler or let it create a default one
    include_session=True,           # include session middleware from config
    include_cors=True,              # include permissive CORS
    login_path="/login",            # where your login view lives within the child app
    allowlist=("/login", "/logout", "/static", "/assets"),  # paths bypassing auth gate
)

# Starlette has the Mount object to handle these situations
app = Starlette(
    routes=[
        Mount(path=admin.url_prefix, app=admin.get_asgi_app())
    ]
)


@app.on_event("startup")
async def start():
    scheduler.start()

@app.on_event("shutdown")
async def stop():
    scheduler.shutdown()
```

As you could see, Starlette uses the `Mount` to assemble ASGI applications. This is how **you should do it**.

The same is applied to FastAPI, Litestar... Each framework that handles ASGI has its mechanism to integrate other ASGI
applications. Asyncz simply made it easier for you by exposing the `get_asgi_app()`.

### Constructor options

- `enable_login: bool`: Turn on auth for the dashboard. If `True`, you must supply `backend`.
- `backend: AuthBackend | None`: The pluggable auth backend (see §6).
- `url_prefix: str | None`: Where to mount the dashboard. Defaults to `settings.dashboard_config.dashboard_url_prefix`. We always normalize trailing slashes.
- `scheduler: AsyncIOScheduler | None`: Your scheduler instance. If omitted, a default in-memory scheduler is created.
- `include_session: bool`: Whether to include `settings.dashboard_config.session_middleware`.
- `include_cors: bool`: Whether to include a permissive CORS middleware for convenience.
- `login_path: str`: Relative path within the child app used by the auth middleware for login redirects.
- `allowlist: tuple[str, ...]`: Paths that bypass the auth check (e.g., `/login`, static assets).

### How it works

- Builds a `Lilya` application with:
    - (optional) CORS middleware
    - (optional) your configured session middleware
    - (optional) `AuthGateMiddleware` (see §6.3)
    - The dashboard routes (root + tasks pages)
    - If `enable_login=True`, adds `/login` and `/logout` routes that delegate to your backend
- **If you are using Lilya**:
    - You mount it by calling `admin.include_in(app)` which does: `app.add_child_lilya(url_prefix, child_app)`
- *If something else**:
    - `get_asgi_app()` is accessible to be used by other frameworks. See [the example](#if-you-are-using-something-else)
for more details.

## Authentication backends

### Built-in backend: `SimpleUsernamePasswordBackend`

A tiny session-backed username/password backend that you can wrap around **any** verification logic you like.

```python
from asyncz.contrib.dashboard.admin import SimpleUsernamePasswordBackend, User, AsynczAdmin
from lilya.apps import Lilya

def verify(username: str, password: str) -> User | None:
    # Real world: check DB, call your identity provider, etc.
    if username == "admin" and password == "secret":
        return User(id="admin", name="Admin")
    return None

app = Lilya()

# renders login template + sets session
backend = SimpleUsernamePasswordBackend(verify=verify)
admin = AsynczAdmin(enable_login=True, backend=backend, url_prefix="/dashboard")
admin.include_in(app)
```

**What it does**

- `GET /login` - renders a friendly login page (your dashboard's Tailwind-styled template).
- `POST /login` - calls your `verify(username, password)`. On success, stores the user session and redirects.
- `/logout` - clears the session and redirects to `/login`.
- `authenticate(request)` - reads the session and returns a `User` if present.

!!! Warning "Security Note"
    You can tailor the session payload to your policy. Some teams store a minimal identifier
    (e.g., `user_id`) and load the user on each request; others serialize a small user object.
    The backend is intentionally simple so you can adjust easily.

### Implement your own backend

Conform to the `AuthBackend` protocol:

```python
from typing import Any
from lilya.requests import Request
from lilya.responses import Response
from asyncz.contrib.dashboard.admin.protocols import AuthBackend, User

class MyTokenBackend(AuthBackend):
    async def authenticate(self, request: Request) -> User | None:
        token = request.headers.get("authorization")
        if not token:
            return None
        # validate token, then:
        return User(id="123", name="Jane Admin")

    async def login(self, request: Request) -> Response:
        # If using token-only auth, you can render a page explaining how to obtain a token,
        # or simply redirect to a provider, or return 405.
        ...

    async def logout(self, request: Request) -> Response:
        # If you use stateless tokens, this might just redirect to /login
        # or call your IdP logout endpoint.
        ...

    def routes(self) -> list[Any]:
        # Optional: return extra Lilya paths if you need them
        return []
```

Then:

```python
admin = AsynczAdmin(enable_login=True, backend=MyTokenBackend(), url_prefix="/dashboard")
admin.include_in(app)
```

### How the gate works (`AuthGateMiddleware`)

- Runs **inside** the child app at your prefix (e.g., `/dashboard`).
- Skips auth for paths in `allowlist` (e.g., `/login`, static assets).
- Calls `backend.authenticate(request)` for all other requests.
- **If not authenticated**:
    - For HTMX requests, returns **401** with `HX-Redirect: /dashboard/login?next=/dashboard/...`
    - Otherwise, returns **303** redirect to `/dashboard/login?next=...`

This means:

- The **full dashboard** is protected.
- **Partial** HTMX updates fail gracefully and trigger a redirect, not a broken fragment.

## Integrating in your application

### Minimal, no-login dashboard

```python
from lilya.apps import Lilya
from asyncz.contrib.dashboard.admin import AsynczAdmin
from asyncz.schedulers.asyncio import AsyncIOScheduler

app = Lilya()
scheduler = AsyncIOScheduler(stores={"default": {"type": "memory"}})

admin = AsynczAdmin(enable_login=False, url_prefix="/dashboard", scheduler=sched)
admin.include_in(app)

@app.on_event("startup")
async def start():
    scheduler.start()
```

Visit: <http://localhost:8000/dashboard>

### With login (simple username/password)

```python
from lilya.apps import Lilya
from asyncz.contrib.dashboard.admin import AsynczAdmin, SimpleUsernamePasswordBackend, User

def verify(u: str, p: str) -> User | None:
    # Replace with DB lookup, password hashing, etc.
    if u == "ops" and p == "supersecret":
        return User(id="ops", name="Ops Admin")
    return None

app = Lilya()
admin = AsynczAdmin(
    enable_login=True,
    backend=SimpleUsernamePasswordBackend(verify),
    url_prefix="/dashboard",
)
admin.include_in(app)
```

### Use a shared scheduler from elsewhere in your app

If your app already constructs and starts `AsyncIOScheduler`, pass that instance to `AsynczAdmin`
so the UI controls the same one:

```python
# somewhere central
sched = AsyncIOScheduler(stores={"default": {"type": "memory"}})

# in your app factory
admin = AsynczAdmin(scheduler=sched, enable_login=False)
admin.include_in(app)
```

### Customizing session / CORS inclusion

```python
admin = AsynczAdmin(
    include_session=True,   # requires that settings.dashboard_config.session_middleware is configured
    include_cors=False,     # turn off built-in permissive CORS if you have your own
)
```

### Customizing login path and allowlist

```python
admin = AsynczAdmin(
    enable_login=True,
    backend=SimpleUsernamePasswordBackend(verify),
    login_path="/signin",
    allowlist=("/signin", "/signout", "/static", "/assets"),
)
```

!!! Check
    The admin will mount `/signin` and `/signout` for you if your backend exposes them
    (the built-in backend mounts `/login` and `/logout` by default, but you can wrap or subclass to change that).

## Real-world recipes

### Use your existing user table

```python
from passlib.hash import bcrypt
from myapp.db import get_user_by_username
from asyncz.contrib.dashboard.admin import SimpleUsernamePasswordBackend, User

def verify(username: str, password: str) - User | None:
    u = get_user_by_username(username)
    if not u or not bcrypt.verify(password, u.password_hash):
        return None
    return User(id=u.id, name=u.display_name, is_admin=u.is_admin)
```

### Only store a minimal session payload

If you prefer to store **only** `user_id` in the session and fetch the user each request:

```python
from asyncz.contrib.dashboard.admin.protocols import AuthBackend, User
from lilya.requests import Request
from lilya.responses import Response, RedirectResponse
from myapp.db import get_user

class DBSessionBackend(AuthBackend):
    def __init__(self, session_key="asyncz_admin_uid"):
        self.session_key = session_key

    async def authenticate(self, request: Request) -> User | None:
        uid = request.session.get(self.session_key)
        if not uid:
            return None
        u = get_user(uid)
        return User(id=u.id, name=u.display_name, is_admin=u.is_admin) if u else None

    async def login(self, request: Request) -> Response:
        if request.method == "GET":
            # render your login template
            ...
        form = await request.form()
        username, password = form.get("username"), form.get("password")
        # validate, then:
        request.session[self.session_key] = user.id
        return RedirectResponse(form.get("next") or "/", status_code=303)

    async def logout(self, request: Request) -> Response:
        request.session.pop(self.session_key, None)
        return RedirectResponse("/login", status_code=303)
```

### API-only protection (header token)

If your deployment serves the dashboard behind a reverse proxy that injects an auth header:

```python
class ProxyHeaderBackend(AuthBackend):
    async def authenticate(self, request: Request) -> User | None:
        sub = request.headers.get("X-Authenticated-User")
        if not sub:
            return None
        return User(id=sub, name=sub)

    async def login(self, request: Request) -> Response:
        # Explain “please login via SSO” or redirect to your provider
        ...

    async def logout(self, request: Request) -> Response:
        # Possibly call IdP logout or just redirect
        ...
```

## Notes & Best Practices

- **Lifecycle.** Start your scheduler on app startup and stop it on shutdown for clean tests and reloads.
- **Security.** Keep the session payload minimal whenever possible, or sign/encrypt cookies if storing anything sensitive.
Prefer server-side lookups (`user_id` - DB fetch).
- **Prefix awareness.** The auth middleware computes redirects correctly under the child mount
(e.g., `/dashboard/login?next=/dashboard/tasks`).
- **HTMX behavior.** Unauthorized HTMX requests return `401` with `HX-Redirect`, so partial updates navigate
to the login page gracefully.
- **Styling.** The login page uses the same Tailwind setup as the dashboard.
Customize the template (e.g., `login.html`) to match your brand.

## API reference

```python
from asyncz.contrib.dashboard import create_dashboard_app    # the actual UI app factory

from asyncz.contrib.dashboard.admin import (
    AsynczAdmin,                     # the wrapper you mount
    SimpleUsernamePasswordBackend,   # built-in backend
    AuthGateMiddleware,              # the gating middleware
    AuthBackend,                     # protocol for custom backends
    User,                            # user value object
)
```

That's it! With `AsynczAdmin`, you get a polished dashboard in minutes and the flexibility to fit your organization's
auth model.
