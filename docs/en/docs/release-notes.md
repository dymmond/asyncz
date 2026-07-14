# Release Notes

## 0.16.0

### Changed

- Updated the release version to `0.16.0`.
- Pinned the dashboard extra to Lilya `0.27.0`.
- Pinned the testing type checker dependency to `ty==0.0.59`.
- Replaced dashboard runtime CDN dependencies with packaged Tailwind CSS,
  Alpine.js CSP, HTMX, Toastify, and favicon assets.
- Rebuilt the dashboard as a modern admin surface with a fixed navigation shell,
  responsive mobile navigation, denser operational tables, Alpine.js-backed
  interaction state, and clearer task action buttons.
- The dashboard task table now shows last-run status and links directly to run
  history details.
- The overview page now includes recent run history alongside scheduler and task
  summaries.

### Added

- Added dashboard static-asset tests that verify local serving, rendered
  template references, and recorded checksum integrity.
- Added scheduler-level status inspection through `scheduler.get_scheduler_info()`
  and the `asyncz status` CLI command.
- Added scheduler identity, start-time, and uptime metadata to runtime
  inspection snapshots, the dashboard runtime page, and `asyncz status --json`.
- Added the `asyncz doctor` CLI command for scheduler diagnostics, readiness
  checks, and strict automation-friendly health validation.
- Added scheduler-backed trigger previews through `scheduler.preview_task_runs()`
  and the `asyncz preview` CLI command.
- Added the `asyncz version` CLI command with JSON output for release and
  packaging smoke checks.
- Added the `asyncz timeline` CLI command for upcoming run previews across all
  tasks.
- Added the `asyncz inspect` CLI command for single-task inspection with
  upcoming run previews and JSON output.
- Added `asyncz add --id` for stable operator-owned task identifiers.
- Added dashboard run history backed by scheduler submission and execution
  events, including manual-vs-scheduled source tracking.
- Added run-detail pages that correlate lifecycle logs and task-scoped logs for
  a specific run id.
- Added dashboard log filtering by `run_id` and structured log extras.
- Added a dashboard runtime page for scheduler timing metadata, stores,
  executors, and per-component task distribution.
- Added a dashboard timeline page that previews upcoming run times across all
  tasks without mutating scheduler state.
- Added a dashboard audit page for task create, run, pause, resume, and remove
  actions.

### Fixed

- Auth-enabled dashboards now allow prefixed static assets such as
  `/dashboard/static/...` through the authentication gate so login pages can load
  packaged CSS and JavaScript.
- Replaced invalid HTMX request attributes in task refresh/action flows with
  valid synchronization behavior.

## 0.15.0

### Added

- Added scheduler-native task inspection APIs through `Task.schedule_state`, `Task.paused`, `Task.snapshot()`, `scheduler.get_task_info()`, and `scheduler.get_task_infos(...)`.
- Added `scheduler.run_task(...)` as the canonical Asyncz-native "run now" operation for administrative and dashboard flows.
- Added richer task filtering and sorting to the CLI `list` command, including task state, executor, trigger, and free-text query support.
- Expanded the dashboard task view with state-aware filtering, richer task metadata, and overview summaries for scheduled, paused, and pending tasks.

### Changed

- Replaced the `loguru` integration with Python's built-in `logging` module across the scheduler, dashboard, CLI examples, and documentation.
- Migrated the documentation stack from `mkdocs-material` to `zensical` and aligned the docs build flow with the current project structure.
- Expanded and corrected the documentation for schedulers, triggers, tasks, stores, executors, ASGI integration, settings, CLI usage, dashboard usage, and API reference material.
- Standardized the development type-checking and linting workflow around Ruff and `ty`.
- The CLI and dashboard now delegate task run, pause, resume, and removal behavior to scheduler-owned APIs instead of maintaining separate control logic.
- Dashboard task rendering now uses immutable task inspection snapshots rather than ad hoc serialization of live task objects.

### Fixed

- Date trigger creation from the CLI and dashboard now uses the correct `run_at` parameter and handles encoded UTC offsets more reliably.
- Dashboard log storage configuration is now shared correctly between log writers and readers when using a custom storage backend.
- Dashboard log records now resolve task identifiers consistently from `task_id`, `job_id`, and `asyncz_task_id`.
- Coroutine execution events now populate the task store alias consistently.
- MongoDB store aliases are now normalized consistently between CLI parsing and scheduler plugin defaults.
- Removed a duplicate executor pool shutdown path.
- Fixed a scheduler `update_task()` recursion path that could surface during pause/resume-style management operations.
- Fixed the dashboard overview page so controller-supplied task summaries and recent-task data are actually rendered.
- Fixed the dashboard overview template link generation.
- Fixed dashboard task filters so they persist across HTMX refreshes and row or bulk actions.
- Fixed manual dashboard runs of one-off tasks so they remain visible in the UI as paused instead of disappearing immediately.

### Removed

- Removed the `loguru` dependency and the `loguru`-based logging backend.

## 0.14.3

### Fixed

- When using the settings it was causing a conflict with the types and not casting properly to the right type due
to the `from future import __annotations__`.

## 0.14.2

### Changed

- Replaced `ChildLilya` sub‑app mounting with `Router`‑based composition for a cleaner and more maintainable architecture.
- `AsynczAdmin` now uses a single composed Lilya app that mounts `/login` and `/logout` at root while serving the dashboard under its prefix.
- Simplified `include_in()` method — mounts the composed app at `/` for proper reverse‑proxy behavior.
- Improved `url_prefix` normalization to avoid double slashes and ensure consistent route generation.
- `Asyncz Dashboard` is now fully reverse-proxy agnostic and works seamlessly behind Nginx or ASGI mounts.

## 0.14.1

### Fixed

- Duplicate dashboard URL prefixing (`/dashboard/tasks/dashboard`) when deployed behind Nginx or under an ASGI mount.
- Nested HTMX table container causing duplicate `#tasks-table` and incorrect `hx-get` paths.

### Changed

- `get_effective_prefix()` now prefers the configured `dashboard_url_prefix` and falls back to `root_path` only when configured as `/`.
- All HTMX and action URLs in the dashboard are now relative to the current path for reverse-proxy compatibility.
- Updated templates to remove hardcoded `/dashboard` from links and actions.
- Asyncz Dashboard is now fully **reverse-proxy ready** (works with `X-Forwarded-Prefix` and ASGI mounts).

## 0.14.0

### Added

- New [settings](./settings.md) module using `ASYNCZ_SETTINGS_MODULE`.
- New [Asyncz client](./cli.md).
- [Asyncz Dashboard](./dashboard.md) allowing to have a UI vision of your current scheduler and tasks.
- Introduced [AsynczAdmin](./dashboard.md#asyncz-dashboard--admin) class for embedding the dashboard directly into Lilya apps.
- Added optional login and session-based authentication through `SimpleUsernamePasswordBackend`.
- Implemented `AuthGateMiddleware` to protect dashboard routes and handle HTMX redirects.
- Added CORS and session middleware support in `AsynczAdmin` with customizable options.
- Integrated `DashboardConfig` access via global settings (`settings.dashboard_config`).
- Introduced detailed documentation and examples for custom `AuthBackend` implementations.
- Support for Python 3.14

### Changed

- Updated internals to allow multiple languages for documentation.
- Documentation structure.

## 0.13.5

### Changed

- Use monkay asgi lifespanHook instead of own implementation.

## 0.13.4

### Changed

- Dropped support for Python 3.9 to match the whole ecosystem.

## 0.13.3

### Fixed

- Different timezones in triggers

## 0.13.2

### Added

- Compatibility with Python 3.13.

## 0.13.1

### Added

- `FileStore` was added (simple synchronization via files in a directory).
- `with_lock` was added to `asyncz.file_locking`.

### Fixed

- SQLAlchemyStore didn't pass extra arguments to create_engine.

## 0.13.0

### Added

- Multi-Processing safe mode.

### Fixed

- `and` was mapped to the wrong trigger.
- Some defaults had wrong module pathes.
- Missing export of NativeAsyncIOScheduler from schedulers.

## 0.12.0

### Added

- `shutdown` trigger.
- Tasks can have a lifecycle.
- NativeAsyncIOScheduler with async start/shutdown methods and some optimizations.

### Fixed

- Raise correct exception when maximal instances are reached.
- Task instances are now per scheduler not per executor.

### Changed

- Invalid executor init kwargs are not ignored anymore.

### Removed

- MaxInterationsReached exception. It had no use and was broken from design.

## 0.11.0

### Added

- Allow submitting paused tasks.
- Allow changing in-place attributes of tasks when submitting with `add_task`.
- Allow selecting alternate logger implementations.
- Allow naming schedulers with an extra logger name.

### Fixed

- `remove_all_tasks` didn't check the store of tasks when pending_tasks was used (stopped scheduler).

### Changed

- Replace `UndefinedType` with `Undefined`. Shim provided for backwards compatibility.
- `add_task` has now more arguments with undefined as default.
- `pending_tasks` has now no more store alias in it.
- `tzlocal` is now optional.
- Tasks use the timezone of the scheduler for their triggers which require a timezone.
- Logging backends became optional.

## 0.10.1

### Added

- Decorated functions have now the `asyncz_tasks` attribute if Tasks are used in decorator mode without a provided `id`.

### Fixed

- Fix backward compatibility in passing functions via fn keyword to add_task

## 0.10.0

### Added

- Task are decorators now.
- Tasks can be added via add_task.
- Trigger can now overwrite `mistrigger_grace_time` via `allow_mistrigger_by_default`.
- Pools can now overwrite `wait` and can set `cancel_futures`.

### Changed

- Task id can be None (decorator mode).
- Task have now pending attribute.
- Tasks work more independent of schedulers.

### Removed

- `schedule_task` call (superseeded by add_task overloads).

### Fixed

- `task_defaults` overwrite settings.
- Fix one-off tasks in background with add_task (before with asgi a misstrigger can happen because of a lag of > 1 second).
- Fix `add_store` call on stopped scheduler.

## 0.9.0

### Added

- SQLAlchemy store
- ASGI integration

### Changed

- Schedulers use now refcounting to track if it should startup/shutdown (for asgi, lifespan).
- Schedulers support now the async and sync context manager protocols.
- Improved typings.
- The default (builtin) plugins live now in `asyncz/scheduler/defaults.py`.

## 0.8.3

### Fixed

- `ref_to_obj` was not considering any functionality that could come from a decorator implementing the `fn`.

## 0.8.2

### Fixed

- `mistrigger_grace_time` from `_setup` was not creating a default.
- Typing clash in the datastructures.

## 0.8.1

### Added

- `threadpool` to the internal mapping.

## 0.8.0

### Fix

- `AsyncIOScheduler` was not pulling the event loop appropriately.
- Fix `mongodb` store finder.

## 0.7.0

### Changed

- `EsmeraldScheduler` contrib register events to match the new Esmerald implementation.

## 0.6.0

### Fixed

#### Breaking change

- In the past, `asyncz` had a typo in `max_intances`. This was changed to `max_instances` instead.
This addresses the Discusson [#49](https://github.com/dymmond/asyncz/discussions/49) raised by [@devkral](https://github.com/devkral).

## 0.5.0

### Changed

- Updated internal `__setstate__` of `Task` to accept also `__pydantic_extra__` and `model_config`.

### Added

- Support for Python 3.12.

### Fixed

- Pydantic 2.0 `__pydantic_extra__` pickling errors.
- Internal issues with MagicMock and Pydantic 2.0

## 0.4.0

### Changed

- Move internal procedure to pydantic 2.0. This process speeds up the internal processing
by leveraging pydantic 2.0 performance.

!!! Warning
    To use this version of Asyncz with Esmerald, until it is announced compatibility with pydantic 2.0 with Esmerald, it is recommended to use Asyncz prior to this release.

## 0.3.1

### Fixed

- `EsmeraldScheduler` attribute update (configurations and timezone).

## 0.3.0

### Changed

- Updated base requirements.
- Fixed linting and parsing of dates and integers.

## 0.2.0

### Changed

- **Breaking changes**: Removed support for python 3.7 as it was limiting the technology from evolving
with the rest of the packages.

## 0.1.4

### Fix

- Store module imports causing issues internally.

## 0.1.3

### Changed

- Updated pyproject to support python 3.11.

## 0.1.2

### Changed

- Update Licence agreement. It was supposed to go in the version 0.1.0

## 0.1.1

### Fixed

- `next_wakeup_time` from base scheedulers wasn't being assigned properly.
- `del timeout` from the asyncio scheduler wasn't being deleted.
- Added missing return on the `process_tasks` causing the waiting time to be None.

## 0.1.0

This release is the first release of Asyncz and it contain all the essentials.

### Added

* **Triggers**
* **Schedulers**
* **Executors**
* **Stores**
* **Events**
* **Contrib**
