# Jobs

Big part of the Asyncz are the Jobs. Those are special objects with instructions and parameters
that are created/sent to the [scheduler](./schedulers.md) and then executed.

Importing a job is as simple as:

```python
from asyncz.jobs import Job
```

## Parameters

* **id** - The unique identifier of this job.
* **name** - The description of this job.
* **fn** - The callable function to execute.
* **args** - Positional arguments to the callable.
* **kwargs** - Keyword arguments to the callable.
* **coalesce** - Whether to only run the job once when several run times are due.
* **trigger** - The trigger object that controls the schedule of this job.
* **executor** - The name of the executor that will run this job.
* **mistrigger_grace_time** - The time (in seconds) how much this job's execution is allowed to
be late (None means "allow the job to run no matter how late it is").
* **max_instances** - The maximum number of concurrently executing instances allowed for this job.
* **next_run_time** - The next scheduled run time of this job.

## Create a job

Creating a job is as simple as:

```python
{!> ../docs_src/jobs/create_job.py !}
```

## Update a job

You can also update a specific job and its properties directly.

```python hl_lines="26-30"
{!> ../docs_src/jobs/update_job.py !}
```

Internally the job is using the given scheduler to be updated and then executed.

!!! Warning
    All attributes can be updated **but the id** as this is immutable.

## Reschedule a job

You can also reschedule a job when need and by that what it means is **changing its trigger only**.

The trigger must be the [alias of the trigger object](./triggers.md#alias).

```python hl_lines="26-30"
{!> ../docs_src/jobs/reschedule_job.py !}
```


## Note

These is in raw terms what a job instance does and how to create a job but 99% of the times you
will not work directly with a job instance like this, instead, you will be creating a job using the
[scheduler](./schedulers.md#adding-jobs) to help you out and it is **strongly advised** to use
the scheduler and the operations via scheduler instead of working directly via job instance.