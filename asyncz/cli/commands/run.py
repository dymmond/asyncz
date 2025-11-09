from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from typing import Annotated, Any

from sayer import Argument, Option, command, info

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.executors.base import BaseExecutor
from asyncz.schedulers import AsyncIOScheduler
from asyncz.stores.base import BaseStore
from asyncz.tasks import Task as AsynczTask


@command
def run(
    job_id: Annotated[str, Argument(help="Job ID to run now")],
    bootstrap: Annotated[
        str | None,
        Option(
            None,
            help="Dotted path to a class with get_scheduler(), e.g. 'ravyn.contrib.asyncz:AsynczSpec'",
        ),
    ],
    store: Annotated[list[str], Option([], "--store", help="Store spec alias=value. Repeatable.")],
) -> None:
    """
    Trigger a job to run immediately.

    This command loads the specified job, forces it to execute on its assigned
    executor, and then updates its internal schedule state (next run time) in the store.

    Examples:

        asyncz run <job_id>
        asyncz run <job_id> --store durable=sqlite:///scheduler.db
    """
    loop: asyncio.AbstractEventLoop = ensure_loop()

    async def main() -> None:
        """The core asynchronous logic for running the job immediately."""
        bootstrap_mode = bool(bootstrap)
        if bootstrap_mode:
            if store:
                info("Using --bootstrap; ignoring --store flag.")

            scheduler: AsyncIOScheduler = load_bootstrap_scheduler(bootstrap)  # type: ignore[arg-type]
            # Try starting the scheduler if not already running
            with contextlib.suppress(Exception):
                await maybe_await(scheduler.start())
        else:
            # 1. Build configuration and initialize a temporary scheduler
            cfg: dict[str, dict[str, Any]] = {"stores": build_stores_map(store)} if store else {}
            scheduler = AsyncIOScheduler(**cfg)
            await maybe_await(scheduler.start())

        # 2. Look up the task and its associated store
        task: AsynczTask
        store_alias: str

        # raises TaskLookupError if missing
        task, store_alias = scheduler.lookup_task(job_id, None)  # type: ignore

        # This assert is necessary to satisfy static analysis after the successful lookup
        assert task is not None

        # 3. Look up the executor
        executor: BaseExecutor = scheduler.lookup_executor(task.executor)  # type: ignore

        # 4. Determine forced run times
        now: datetime = datetime.now(scheduler.timezone)
        run_times: list[datetime] = task.get_run_times(scheduler.timezone, now)

        # If nothing is due according to the schedule, still allow a forced "run now".
        if not run_times:
            run_times = [now]

        # 5. Submit the task to the executor
        executor.send_task(task, run_times)

        # 6. Update schedule state
        last_run: datetime = run_times[-1]

        # Calculate the *new* next run time based on the last run time
        next_run: datetime | None = task.trigger.get_next_trigger_time(  # type: ignore
            scheduler.timezone, last_run, now
        )

        if next_run:
            # Update the in-memory task object and persist directly to the store
            task.update_task(next_run_time=next_run)
            store_obj: BaseStore = scheduler.lookup_store(store_alias)  # type: ignore
            store_obj.update_task(task)
        else:
            # No further runs – remove task from its store.
            scheduler.delete_task(task.id, store_alias)

        info(f"Triggered job {job_id}")

        # 7. Shutdown the temporary scheduler
        if not bootstrap_mode:
            await maybe_await(scheduler.shutdown())

    loop.run_until_complete(main())
