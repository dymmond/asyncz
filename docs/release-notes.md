# Release Notes

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
