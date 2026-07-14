# Vendors

Asyncz has a clear lineage, and the projects that shaped it deserve direct
credit.

## APScheduler

Asyncz started from the APScheduler model and was rewritten around Pydantic,
async Python applications, ASGI lifecycle integration, and the operational
workflows Asyncz needs to support.

That means APScheduler is the foundation and the project deserves attribution.
It does not mean Asyncz is a drop-in copy of every APScheduler release.
Asyncz keeps the familiar scheduler, trigger, store, executor, and task model
while making its own choices for configuration, dashboard operations, CLI
inspection, run history, and logging.

### Attribution

Asyncz is primarily an APScheduler rewrite with Pydantic and Asyncz-specific
runtime, dashboard, and CLI behavior. The attribution for the original
scheduling model goes to APScheduler.

### Commit MIT license

By the time of the use of the license, the latest commit is linked to:

https://github.com/agronholm/apscheduler/commit/3205a400a5f0ee4677cef082f6c50570c7004edf

## Dashboard browser assets

The optional dashboard vendors its runtime browser assets as package resources
so installed deployments do not depend on public CDNs.

The current vendored assets are:

- Alpine.js CSP from npm `@alpinejs/csp`
- Tailwind CSS from npm `tailwindcss` and `@tailwindcss/cli`
- HTMX from npm `htmx.org`
- Toastify from npm `toastify-js`

Checksums, npm integrity values, upstream tarball URLs, and license file paths
are recorded in `asyncz/contrib/dashboard/statics/vendor/manifest.json`.
