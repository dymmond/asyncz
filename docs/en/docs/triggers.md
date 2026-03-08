# Triggers

Triggers decide when a task should run next. Every task has exactly one trigger instance.

## Built-in trigger aliases

- `date`
- `interval`
- `cron`
- `and`
- `or`
- `shutdown`

## `DateTrigger`

Runs a task once at a specific point in time.

- Alias: `date`

```python
{!> ../../../docs_src/triggers/date/example1.py !}
```

```python
{!> ../../../docs_src/triggers/date/example2.py !}
```

If you omit `run_at`, Asyncz schedules the task for immediate execution.

```python
{!> ../../../docs_src/triggers/date/example3.py !}
```

## `IntervalTrigger`

Runs a task repeatedly at a fixed interval.

- Alias: `interval`

Supported parameters include:

- `weeks`
- `days`
- `hours`
- `minutes`
- `seconds`
- `start_at`
- `end_at`
- `timezone`
- `jitter`

```python
{!> ../../../docs_src/triggers/interval/example1.py !}
```

```python
{!> ../../../docs_src/triggers/interval/example2.py !}
```

```python
{!> ../../../docs_src/triggers/interval/example3.py !}
```

```python
{!> ../../../docs_src/triggers/interval/example4.py !}
```

## `CronTrigger`

Runs a task according to cron-style rules.

- Alias: `cron`

Useful parameters include:

- `year`
- `month`
- `day`
- `week`
- `day_of_week`
- `hour`
- `minute`
- `second`
- `start_at`
- `end_at`
- `timezone`
- `jitter`

```python
{!> ../../../docs_src/triggers/cron/example1.py !}
```

```python
{!> ../../../docs_src/triggers/cron/example2.py !}
```

```python
{!> ../../../docs_src/triggers/cron/example3.py !}
```

```python
{!> ../../../docs_src/triggers/cron/example4.py !}
```

## Combination triggers

### `AndTrigger`

Returns the earliest next time that all child triggers agree on.

- Alias: `and`

```python
{!> ../../../docs_src/triggers/combination/and.py !}
```

### `OrTrigger`

Returns the earliest next time produced by any child trigger.

- Alias: `or`

```python
{!> ../../../docs_src/triggers/combination/or.py !}
```

## `ShutdownTrigger`

Runs once when the scheduler shuts down. This is useful for cleanup hooks and lifecycle-style task patterns.

- Alias: `shutdown`

```python
{!> ../../../docs_src/triggers/shutdown.py !}
```

## Custom triggers

Custom triggers must subclass `BaseTrigger` and implement `get_next_trigger_time(...)`.

```python
{!> ../../../docs_src/triggers/custom.py !}
```
