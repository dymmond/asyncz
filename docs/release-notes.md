# Release Notes

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
