# Schedulers

Schedulers are the *thing* that makes all magic and binds everything together. You can see it as a
glue.

Usually the developer does not deal/handle the [stores](./stores.md), [executors](./executors.md)
or even [triggers](./triggers.md) manually, instead that is managed by the scheduler that acts
as an interface amongst them all.

Asyncz being dedicated to ASGI and asyncio brings the [AsyncIOScheduler](#asyncioscheduler)
out of the box and only supports this one natively but like everything in Asyncz, you can also
create your own [custom scheduler](#custom-scheduler) that does not necessarily need to be for
async. You can build your own scheduler for blocking/background applications.

In fact, Asyncz is used by [Esmerald](https://esmerald.dymmond.com) as internal scheduling system
and uses the [supported scheduler](./contrib/esmerald/scheduler.md) from Asyncz to perform its
tasks.

## Configuring the scheduler

Due its simplificy, Asyncz provides some ways of configuring the scheduler for you.

=== "In a nutshell"

    ```python
    from asyncz.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    ```

=== "From the schedulers"

    ```python
    from asyncz.schedulers import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    ```

**What is happening here?**:

When you create the scheduler like the examples above, it is creating an [AsyncIOScheduler](#asyncioscheduler)
with a [MemoryStore](./stores.md#memorystore) named `default` and starting the
<a href='https://docs.python.org/3/library/asyncio-eventloop.html' target='_blank'>asyncio event loop</a>.

### Example configuration

Let us assume you now need a very custom configuration with more than one store, executors and
custom settings.

* Two stores - A [mongo](./stores.md#mongo) and a [redis](./stores.md#redis).
* Two executors - An [asyncio](./executors.md#asyncioexecutor) and
a [thread pool](./executors.md#threadpoolexecutor).
* Coalesce turned off for new jobs by default.
* Maximum instance limiting to 4 for new jobs.

#### First option

The first way of doing the configuration is in a simple pythonic fashion.

```python
{!> ../docs_src/schedulers/method1.py !}
```

#### Second option

The second option is by starting the scheduler and injecting a dictionary directly upon
instantiation.

```python
{!> ../docs_src/schedulers/method2.py !}
```

#### Third option

The third option is by starting the scheduler and use the `configure` method.

```python
{!> ../docs_src/schedulers/method3.py !}
```

## Starting and stopping the scheduler

Every scheduler inherits from the [BaseScheduler](#basescheduler) and therefore implement the
mandatory functions such as `start` and `shutdown`.

To start the scheduler simply run:

```python
{!> ../docs_src/schedulers/start.py !}
```

To stop the scheduler simply run:

```python
{!> ../docs_src/schedulers/shutdown.py !}
```

## Adding jobs

A scheduler to work needs jobs, of course and Asyncz offers some ways of adding jobs into the
scheduler.

* [add_jobs](#add-jobs)
* [scheduled_jobs](#scheduled-jobs)

There is also a third option but that is related with the integration with ASGI frameworks, for
instance [esmerald](./contrib/esmerald/decorator.md) which it should not be used in this agnostic
context.

### Add jobs

Adding a job via `add_job` is the most common and probably the one you will be using more times
than the `scheduled_job`.

**The `add_job` returns an instance of [Job](./jobs.md).**

So, how can you add a job?

```python hl_lines="26-29 32-38 41-47"
{!> ../docs_src/schedulers/add_job.py !}
```

What happen here is actually very simple. We created an instance of the `AsyncIOScheduler` and
added the functions `send_email_newsletter`, `collect_www_info`, `check_status` to the scheduler
and started it.

Why then passing `CronTrigger` and `IntervalTrigger` instances instead of simply passing `cron`
or `interval`?

Well, we want to pass some attributes to the object and this way makes it cleaner
and simpler.

When adding jobs there is not a specific order. **You can add jobs at any given time**. If the
scheduler is not yet running, once it does it will add the jobs to it.

## Scheduled jobs

Scheduled jobs works in the same way as [add_jobs](#add-jobs) with the **unique difference** that
the `replacing_existing` is always `True` and it is used as a decorator.

```python hl_lines="10-12 19-23 29-33"
{!> ../docs_src/schedulers/scheduled_job.py !}
```

## Deleting jobs

In the same way you can [add jobs](#add-jobs) you can also remove them with the same ease and there
are also different ways of removing them.

* [delete_job](#delete-job)
* [delete](#delete)

### Delete job

This is probably the most common way of removing jobs from the scheduler using the job id and the
store alias.

```python hl_lines="27 34 40 41"
{!> ../docs_src/schedulers/delete_job.py !}
```

## Delete

The `delete` function is probably more convenient but it requires that you store the [Job](./jobs)
somewhere ocne the instance is received and for jobs scheduled by [scheduled job](#scheduled-jobs)
this method does not work, instead only the [delete job](#delete-job) will work.

```python hl_lines="23 29"
{!> ../docs_src/schedulers/delete.py !}
```

## Pause and resume job

As shown above, you can add and remove jobs but you can pause and resume jobs as well. When a job
is paused, there is no next time to run since the action is no longer being validate. That can be
again reactivated by resuming that same [Job](./jobs).

Like the previous examples, there are also multiple ways of achieving that.

* [pause_job](#pause-job)
* [pause](#pause)
* [resume_job](#resume-job)
* [resume](#resume)

### Pause job

Like [delete_job](#delete-job), you can pause a job using the id.

```python hl_lines="22 29 35-36"
{!> ../docs_src/schedulers/pause_job.py !}
```

### Pause

The same is applied to the simple pause where you can do it directly via job instance.

```python hl_lines="23 29"
{!> ../docs_src/schedulers/pause.py !}
```

### Resume job

Resuming a job is as simple as again, passing a job id.

```python hl_lines="22 29 35-36"
{!> ../docs_src/schedulers/resume_job.py !}
```

### Resume

Same for the resume. You can resume a job directly from the instance.

```python hl_lines="23 29"
{!> ../docs_src/schedulers/resume.py !}
```

## BaseScheduler

## AsyncIOScheduler


## Custom Scheduler