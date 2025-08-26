# Release Notes

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
- Allow selecting logger (classical, loguru).
- Allow naming schedulers with an extra logger name.

### Fixed

- `remove_all_tasks` didn't check the store of tasks when pending_tasks was used (stopped scheduler).

### Changed

- Replace `UndefinedType` with `Undefined`. Shim provided for backwards compatibility.
- `add_task` has now more arguments with undefined as default.
- `pending_tasks` has now no more store alias in it.
- `tzlocal` is now optional.
- Tasks use the timezone of the scheduler for their triggers which require a timezone.
- `loguru` is now optional.

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
