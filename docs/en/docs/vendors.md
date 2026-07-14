# Vendors

There are vendors that inspired Asyncz that deserve to be mentioned.

## APScheduler

Although Asyncz is not Apscheduler there is no deny that the base was and although completely
rewritten in Pydantic and with a different structure and use cases, we believe it is worth
mention APScheduler and the main reason is simply because it wouldn't be possible to have Asyncz
without APScheduler and we used the same level of testing as the library to make sure we were
covering the needed use cases but not all of them as Asyncz has a different target.

### Attribution

Asyncz is mainly the APScheduler rewritten with Pydantic and with some changes to be compliant
with some of the new use cases covered by Asyncz and therefore the attribution goes to APScheduler.

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
