# Triggers

In simple terms, a trigger is what contains the logic for the [scheduler](./schedulers.md) to
execute. Internal tasks contain their own trigger which checks when a task should be the next to run.

There are five types of triggers available within the Asyncz.

All the triggers subclass the [BaseTrigger](#basetrigger) and any custom trigger should be
the same.

## DateTrigger

The DateTrigger is the simplest way of scheduling a task. It schedules a task to be executed once
at a given time.

**alias** - `date`

### Parameters

* **run_at** - The date/time to run the task at.

    <sup>Default: `None`</sup>

* **timezone** - The time zone for the run_at if it does not have one already.
  
  <sup>Default: `None`</sup>

#### Examples

```python hl_lines="14"
{!> ../docs_src/triggers/date/example1.py !}
```

You can run the trigger by passing a date as text as well.

```python hl_lines="12"
{!> ../docs_src/triggers/date/example2.py !}
```

Do you want to run immediatly after adding the task? Don't specify any date then.

```python hl_lines="12"
{!> ../docs_src/triggers/date/example3.py !}
```

## IntervalTrigger

If you want to run the task periodically, this is the trigger for you then. The advantage of this
trigger is that you can specify also the `start_at` and `end_at` making it more custom for your
needs.

**alias** - `interval`

### Parameters

* **weeks** - Number of weeks to wait.

    <sup>Default: `0`</sup>

* **days** - Number of days to wait.

    <sup>Default: `0`</sup>

* **hours** - Number of hours to wait.

    <sup>Default: `0`</sup>

* **minutes** - Number of minutes to wait.

    <sup>Default: `0`</sup>

* **seconds** - Number of seconds to wait.

    <sup>Default: `0`</sup>

* **start_at** - Starting point for the interval calculation.

    <sup>Default: `None`</sup>

* **end_at** - Latest possible date/time to trigger on.

    <sup>Default: `None`</sup>

* **timezone** - Time zone to use gor the date/time calculations.

    <sup>Default: `None`</sup>

* **jitter** - Delay the task execution by jitter seconds at most.

    <sup>Default: `None`</sup>

#### Examples

```python hl_lines="12"
{!> ../docs_src/triggers/interval/example1.py !}
```

Use the `start_at` and `end_at` to provide a limit in which the scheduler should run.

```python hl_lines="12-14"
{!> ../docs_src/triggers/interval/example2.py !}
```

What about using the `scheduled_task` decorator?

```python hl_lines="8"
{!> ../docs_src/triggers/interval/example3.py !}
```

What is the jitter? A simple random component that can be added to the execution. This can be
useful if there are multiple server running tasks and you don't want them to run the same task
at the exact same time or to prevent the same task to run concurrently.

```python hl_lines="12"
{!> ../docs_src/triggers/interval/example4.py !}
```

## CronTrigger

This is similar to a UNIX cron like system and the most powerful trigger in Asyncz.
The possiblities of this cron are endless and this can be also frightning if you are not familiar
with how UNIX crons operate.

!!! Tip
    Get familiar with the
    <a href="https://www.ibm.com/docs/en/db2oc?topic=task-unix-cron-format" target="_blank">
    UNIX cron</a> and take advantage of the `CronTrigger` with ease.

A visual explanation of how a UNIX cron is might also help.

```shell
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of the month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of the week (0 - 6) (Sunday to Saturday;
│ │ │ │ │                                   7 is also Sunday on some systems)
│ │ │ │ │
│ │ │ │ │
* * * * * <command to execute>
```

Like the [IntervalTrigger](#intervaltrigger), you can also specify a `start_at` and an `end_at`
parameters.

Since Asyncz is APScheduled revamped, it also inherited the CronTrigger in the way it was
beautifully done which means you can omit fields that you don't need.

**alias** - `cron`

### Parameters

* **year** - 4-digit value.

    <sup>Default: `None`</sup>

* **month** - Month (1-12).

    <sup>Default: `None`</sup>

* **day** - Day of the month (1-31).

    <sup>Default: `None`</sup>

* **week** - ISO week (1-53).

    <sup>Default: `None`</sup>

* **day_of_week** - Number or name of weekday (0-6 or mon,tue,wed,thu,fri,sat,sun).

    <sup>Default: `None`</sup>

* **hour** - Hour (0-23).

    <sup>Default: `None`</sup>

* **minute** - Minute (0-59).

    <sup>Default: `None`</sup>

* **second** - Second (0-59).

    <sup>Default: `None`</sup>

* **start_at** - Earliest possible date/time to trigger on (inclusive).

    <sup>Default: `None`</sup>

* **end_at** - Latest possible date/time to trier on (inclusive).

    <sup>Default: `None`</sup>

* **timezone** - Time zone to use for the date/time calculations (defaults to scheduler timezone).

    <sup>Default: `None`</sup>

* **jitter** - Delay the task executions by jitter seconds at most.

    <sup>Default: `None`</sup>

### Expressions

The table below lists all the available expressions for the use in the fields from year to second.

Multiple expressions can be given in a single field (comma separated).

| Expression | Field | Description |
| ---------- | ----- | ----------- |
| `*`        | any   | Fire on every clause |
| `*/n`      | any   | For every `n` values, staring from the minimum |
| `a-n`      | any   | Fire on any value within the `a-n` range (a must be smaller than n) |
| `a-b/n`    | any   | Fire every `n` values within the `a-b` range |
| `xth y`    | day   | Fire on the `x` -th occurrence of weekday `y` within the month |
| `last x`   | day   | Fire on the last occurrence of weekday `x` within the month |
| `last`     | day   | Fire on the last day within the month |
| `x,y,z`    | any   | Fire on any matching expression; can combine any number of any of the above expressions |

!!! Info
    The `month` and `day_of_week` accept abbreviated English month and weekday names. 
    Example: `jan` - `dec` and `mon` - `sun` respectively.

### Daylight saving time behaviour

As mentioned numerous times, Asyncz comes from APScheduler and therefore similar behaviours were
implemented and with also means the cron trigger works with the so-called "wall clock" time. If the
selected time zone observes DST (daylight saving time), you should be aware that it may cause
unexpected behavior with the cron trigger when entering or leaving DST.

**Example of a problematic schedule**:

```python
# In the Europe/London timezone, this will not execute at all on the last sunday morning of March
# Likewise, it will execute twice on the last sunday morning of October
scheduler.add_task(my_task, 'cron', hour=4, minute=25)
```

#### Examples

```python hl_lines="15"
{!> ../docs_src/triggers/cron/example1.py !}
```

Use the `start_at` and `end_at` to provide a limit in which the scheduler should run.

```python hl_lines="14"
{!> ../docs_src/triggers/cron/example2.py !}
```

What about using the `scheduled_task` decorator?

```python hl_lines="7"
{!> ../docs_src/triggers/cron/example3.py !}
```

What about some jitter?

```python hl_lines="11"
{!> ../docs_src/triggers/cron/example4.py !}
```

## Combination

The combinator is a special instance that allows joining different triggers in one place. Imagine
in SQL when you use the `AND` and `OR` operators. This works in a similar fashion.

There are two combinators available, the [OrTrigger](#ortrigger) and the [AndTrigger](#andtrigger).

### AndTrigger

Always returns the earliest next trigger time that all the given trigger can agree on. The trigger
is considered to be finished when any of the given triggers has finished the schedule.

**alias** - `and`

#### Parameters

* **triggers** - List of triggers to combine.
* **jiter** - Delay the task execution by the jitter seconds at most.

    <sup>Default: `None`</sup>

##### Examples

```python hl_lines="13 17"
{!> ../docs_src/triggers/combination/and.py !}
```

### OrTrigger

Always returns the earliest next trigger produced by any of the given triggers. The trigger
is considered to be finished when all of the given triggers have finished their schedule.

**alias** - `or`

#### Parameters

* **triggers** - List of triggers to combine.
* **jiter** - Delay the task execution by the jitter seconds at most.

    <sup>Default: `None`</sup>

##### Examples

```python hl_lines="13-15 18"
{!> ../docs_src/triggers/combination/or.py !}
```

## BaseTrigger

All the triggers subclass the BaseTrigger and any [custom trigger](#custom-trigger) must be the
same.

```python
from asyncz.triggers.base import BaseTrigger
```

## Custom trigger

If you see the triggers provided are not good enough for your use cases, you can always create
one of your own and **you must** implement the **get_next_trigger_time()** on your custom trigger.

```python
{!> ../docs_src/triggers/custom.py !}
```

### Alias

Every trigger has an alias that sometimes and based on the given examples is passed instead of
the object instance itself.

* [DateTrigger](#datetrigger) - `date`
* [IntervalTrigger](#intervaltrigger) - `interval`
* [CronTrigger](#crontrigger) - `cron`
* [AndTrigger](#andtrigger) - `and`
* [OrTrigger](#ortrigger) - `or`
