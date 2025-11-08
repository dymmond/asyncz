from __future__ import annotations

from datetime import datetime
from typing import Annotated

from sayer import Argument, Option, command, info

from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler


@command
def run(
    job_id: Annotated[str, Argument(help="Job ID to run now")],
    store: Annotated[list[str], Option([], "--store", help="Store spec alias=value. Repeatable.")],
):
    """Trigger a job to run immediately."""
    loop = ensure_loop()

    async def main():
        cfg = {"stores": build_stores_map(store)} if store else {}
        sched = AsyncIOScheduler(**cfg)
        await maybe_await(sched.start())

        # Manually submit the task to the executor once, mirroring the scheduler's internal flow.
        task, store_alias = sched.lookup_task(job_id, None)  # raises TaskLookupError if missing
        assert task is not None
        executor = sched.lookup_executor(task.executor)  # type: ignore[arg-type]

        # Emulate the scheduler's calculation of run times and next run.
        now = datetime.now(sched.timezone)
        run_times = task.get_run_times(sched.timezone, now)
        # If nothing is due according to the schedule, still allow a forced "run now".
        if not run_times:
            run_times = [now]

        # Submit and then advance schedule based on the last actual run time.
        executor.send_task(task, run_times)

        last_run = run_times[-1]
        next_run = task.trigger.get_next_trigger_time(sched.timezone, last_run, now)  # type: ignore[union-attr]
        if next_run:
            # Update the in-memory task object and persist directly to the store to avoid
            # dispatching events/wakeup that could recurse while we're in a manual run.
            task.update_task(next_run_time=next_run)
            sched.lookup_store(store_alias).update_task(task)  # type: ignore[arg-type]
        else:
            # No further runs – remove task from its store.
            sched.delete_task(task.id, store_alias)

        info(f"Triggered job {job_id}")
        await maybe_await(sched.shutdown())

    loop.run_until_complete(main())
