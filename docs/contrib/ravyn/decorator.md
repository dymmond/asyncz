# Decorator

The decorator is a wrapper provided by Asyncz to Ravyn that allows you to declare tasks
anywhere and import them into the [RavynScheduler](./scheduler.md) upont instantiation.

In the end, the scheduler is a wrapper on te top of the [Task](../../tasks.md) object but not the
same as the [task decorator](../../schedulers.md#add-tasks-as-decorator). The latter is to be used
outside of the Ravyn context.

## Parameters

* **name** - Textual description of the task.

    <sup>Default: `None`</sup>

* **trigger** - An instance of a trigger class.

    <sup>Default: `None`</sup>

* **id** - Explicit identifier for the task.

    <sup>Default: `None`</sup>

* **mistrigger_grace_time** - Seconds after the designated runtime that the task is still
    allowed to be run (or None to allow the task to run no matter how late it is).

    <sup>Default: `None`</sup>

* **coalesce** - Run once instead of many times if the scheduler determines that the
    task should be run more than once in succession.

    <sup>Default: `None`</sup>

* **max_instances** - Maximum number of concurrently running instances allowed for this
    task.

    <sup>Default: `None`</sup>

* **next_run_time** - When to first run the task, regardless of the trigger (pass
    None to add the task as paused).

    <sup>Default: `None`</sup>

* **store** - Alias of the task store to store the task in.

    <sup>Default: `default`</sup>

* **executor** - Alias of the executor to run the task with.

    <sup>Default: `default`</sup>

* **replace_existing** -  True to replace an existing task with the same id
    (but retain the number of runs from the existing one).

    <sup>Default: `None`</sup>

* **args** - List of positional arguments to call func with.

    <sup>Default: `None`</sup>

* **kwargs** - Dict of keyword arguments to call func with.

    <sup>Default: `None`</sup>

* **is_enabled** -  True if the the task to be added to the scheduler.

    <sup>Default: `None`</sup>

### Examples

Using the decorator is quite straightforward and clear. You can place a task anywhere in your
application, declare the decorator on the top of the task and then import it inside your Ravyn
instance.

Let us assume:

* You have some tasks living inside a file `src/accounts/tasks.py`.
* You want to import them inside your Ravyn application.

```python hl_lines="8 14 20 29-33"
{!> ../docs_src/contrib/ravyn/decorator.py !}
```
