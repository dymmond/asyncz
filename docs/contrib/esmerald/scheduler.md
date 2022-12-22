# Scheduler

Esmerald internally uses Asyncz to perform its tasks if need and the main object used is the
`EsmeraldScheduler`.

Can you use this externally? Very unlikely. This serves only for the purpose of explaining how
and what the object does as internally, by the time of this writting, Esmerald does not allow
to pass specific schedulers, instead, uses this one out of the box.

## EsmeraldScheduler

The object that is instantiated when an Esmerald application is created and the scheduler is
enabled.

Esmerald also defaults the `scheduler_class` to the
Asyncz [AsyncIOScheduler](../../schedulers.md#asyncioscheduler) if nothing is provided.

### Parameters

* **app** - Esmerald instance.
* **scheduler_class** - An instance of a [scheduler](../../schedulers.md).
* **tasks** - A dictinary str, str mapping the tasks of the application to be executed.
* **timezone** - The timezone instance.
* **configurations** - A dictionary with extra configurations to be passed to the
[scheduler](../../schedulers.md).

#### Example

This is how Esmerald usually works. Let us assume:

* You have some tasks living inside a file `src/accounts/tasks.py`.
* You want to pass some extra configurations to the scheduler.

```python hl_lines="42-48"
{!> ../docs_src/contrib/esmerald/scheduler.py !}
```

As stated above, this is just an illustration on how Esmerald operates with Asyncz
(from the version 0.5.0 onwards) and shows how you can use your usual configurations of Asyncz
directly with the framework
