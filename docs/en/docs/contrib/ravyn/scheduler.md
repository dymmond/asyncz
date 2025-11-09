# Scheduler

Ravyn internally uses Asyncz to perform its tasks if need and the main object used is the
`RavynScheduler`.

Can you use this externally? Very unlikely. This serves only for the purpose of explaining how
and what the object does as internally, by the time of this writting, Ravyn does not allow
to pass specific schedulers, instead, uses this one out of the box.

## RavynScheduler

The object that is instantiated when an Ravyn application is created and the scheduler is
enabled.

Ravyn also defaults the `scheduler_class` to the
Asyncz [AsyncIOScheduler](../../schedulers.md#asyncioscheduler) if nothing is provided.

!!! Warning
    By the time this document was written, Ravyn was in version 0.5.0 and it did not allow
    passing different `RavynScheduler` instance on instantiation time but that might change
    in the future. In other words, this is just an explanation of how does the object work
    internally.

### Parameters

* **app** - Ravyn instance.
* **scheduler_class** - An instance of a [scheduler](../../schedulers.md).
* **tasks** - A dictinary str, str mapping the tasks of the application to be executed.
* **timezone** - The timezone instance.
* **configurations** - A dictionary with extra configurations to be passed to the
[scheduler](../../schedulers.md).

#### Example

This is how Ravyn usually works. Let us assume:

* You have some tasks living inside a file `src/accounts/tasks.py`.
* You want to pass some extra configurations to the scheduler.

```python hl_lines="42-48"
{!> ../../../docs_src/contrib/ravyn/scheduler.py !}
```

As stated above, this is just an illustration on how Ravyn operates with Asyncz
(from the version 0.5.0 onwards) and shows how you can use your usual configurations of Asyncz
directly with the framework

## Functionalities

`RavynScheduler` does the heavy lifting for you.

* Registers the tasks in the Asyncz scheduler based on the `tasks` parameters.
* Registers the Ravyn events `startup` and `shutdown` automatically on app instantiation.
