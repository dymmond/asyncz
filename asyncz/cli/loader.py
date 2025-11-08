from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from asyncz.schedulers import AsyncIOScheduler
from asyncz.tasks import Task


async def load_jobs_from_module(scheduler: AsyncIOScheduler, module_path: str) -> int:
    """
    Accepts 'pkg.jobs:registry'. 'registry' may be a list[dict] or a callable(scheduler)->list[dict].
    Each dict: {func: 'pkg.mod:callable', trigger: <Trigger>, args: [], kwargs: {}}
    """
    mod_name, _, attr = module_path.partition(":")
    module = importlib.import_module(mod_name)
    obj = getattr(module, attr) if attr else module
    entries = obj(scheduler) if callable(obj) else obj

    added = 0
    for item in entries:  # type: ignore
        task = Task(func=item["func"], name=item.get("name"))
        scheduler.add_task(
            task,
            trigger=item["trigger"],
            args=item.get("args", []),
            kwargs=item.get("kwargs", {}),
        )
        added += 1
    return added


async def load_jobs_from_config(scheduler: AsyncIOScheduler, path: str) -> int:
    """
    YAML/JSON format:
      jobs:
        - name: ping
          func: mypkg.jobs:ping
          cron: "*/5 * * * *"
        - name: report
          func: mypkg.jobs:send_report
          interval: "10m"
    """
    p = Path(path)
    data: dict[str, Any]
    if p.suffix in {".yml", ".yaml"}:
        import yaml  # optional dependency

        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    else:
        data = json.loads(p.read_text(encoding="utf-8"))

    from .types import parse_trigger

    added = 0
    for job in data.get("jobs", []):
        trig = parse_trigger(cron=job.get("cron"), interval=job.get("interval"), at=job.get("at"))
        task = Task(func=job["func"], name=job.get("name"))
        scheduler.add_task(
            task, trigger=trig, args=job.get("args", []), kwargs=job.get("kwargs", {})
        )
        added += 1
    return added
