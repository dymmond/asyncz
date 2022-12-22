# Release Notes

## 0.1.1

December 22, 2022.

### Fixed

- `next_wakeup_time` from base scheedulers wasn't being assigned properly.
- `del timeout` from the asyncio scheduler wasn't being deleted.
- Added missing return on the `process_tasks` causing the waiting time to be None.

## 0.1.0

December 22, 2022.

This release is the first release of Asyncz and it contain all the essentials.

### Added

* **Triggers**
* **Schedulers**
* **Executors**
* **Stores**
* **Events**
* **Contrib**
