from __future__ import annotations

from datetime import datetime
from typing import Any

from lilya.requests import Request
from lilya.responses import HTMLResponse

from asyncz.contrib.dashboard.engine import templates
from asyncz.triggers.cron import CronTrigger
from asyncz.triggers.date import DateTrigger
from asyncz.triggers.interval import IntervalTrigger


def serialize(task: Any) -> dict[str, Any]:
    """
    Serializes an Asyncz Task object into a standardized dictionary format suitable for
    JSON response or dashboard rendering.

    Args:
        task: The Asyncz Task object to serialize.

    Returns:
        A dictionary containing key task details, with `next_run_time` formatted as an ISO string.
    """
    # Determine trigger type name, fallback to '-'
    trigger: str = type(task.trigger).__name__ if getattr(task, "trigger", None) else "-"

    # Get next_run_time
    nrt: datetime | Any = getattr(task, "next_run_time", None)

    # Format next_run_time as an ISO string if it's a datetime object
    nrt_s: str | None = nrt.isoformat() if isinstance(nrt, datetime) else (nrt or None)

    return {
        "id": task.id,
        "name": task.name or "",
        "trigger": trigger,
        "next_run_time": nrt_s,
        "store": task.store or "default",
        "executor": task.executor or "default",
    }


def parse_trigger(trigger_type: str, trigger_value: str | None = None) -> Any:
    """
    Parses a simplified trigger specification (type + value) into an instantiated
    Asyncz trigger object.

    The parser covers:
      - interval: "10s", "5m", "2h", or plain seconds (fallback)
      - cron: 5-field crontab strings
      - date: ISO 8601 datetime strings

    Args:
        trigger_type: The type of trigger ('interval', 'cron', 'date').
        trigger_value: The value string corresponding to the trigger type.

    Returns:
        An instantiated `BaseTrigger` subclass (`IntervalTrigger`, `CronTrigger`, or `DateTrigger`).

    Raises:
        ValueError: If the trigger type is unsupported, the value format is invalid, or the cron fields are incorrect.
    """
    tt: str = (trigger_type or "").strip().lower()
    tv: str = (trigger_value or "").strip()

    if tt == "interval":
        # IntervalTrigger logic: Supports s, m, h suffix
        try:
            if tv.endswith("s"):
                return IntervalTrigger(seconds=int(tv[:-1]))
            if tv.endswith("m"):
                return IntervalTrigger(minutes=int(tv[:-1]))
            if tv.endswith("h"):
                return IntervalTrigger(hours=int(tv[:-1]))
            # Fallback: treat plain number as seconds
            return IntervalTrigger(seconds=int(tv))
        except ValueError:
            raise ValueError(
                f"Invalid interval value: {tv}. Must be like '10s' or '300'."
            ) from None

    if tt == "cron":
        # CronTrigger logic: Expects standard 5-field string
        parts: list[str] = tv.split()
        if len(parts) != 5:
            raise ValueError("cron must have 5 fields: '*/5 * * * *'")
        return CronTrigger.from_crontab(tv)

    if tt == "date":
        # DateTrigger logic: Expects ISO 8601 datetime string
        try:
            dt_obj: datetime = datetime.fromisoformat(tv)
        except Exception as e:
            raise ValueError(f"Invalid ISO datetime: {tv}") from e
        return DateTrigger(run_date=dt_obj)


async def render_table(scheduler: Any, request: Request) -> HTMLResponse:
    """
    Renders the HTML table fragment for the list of scheduled tasks, supporting optional search filtering.

    Args:
        scheduler: The active `AsyncIOScheduler` instance.
        request: The incoming Lilya Request object, used to retrieve query parameters (search query 'q').

    Returns:
        HTMLResponse: A response containing the rendered `_table.html` template fragment.
    """
    tasks: list[Any] = scheduler.get_tasks()

    # Serialize all tasks
    items: list[dict[str, Any]] = [serialize(t) for t in tasks]

    # Apply optional search filter (q=...)
    q: str | None = request.query_params.get("q") if hasattr(request, "query_params") else None
    if q:
        ql: str = q.lower()
        items = [
            t
            for t in items
            if ql in t["id"].lower()
            or ql in (t["name"] or "").lower()
            or ql in (t["store"] or "").lower()
        ]

    # Render the table template
    html: str = templates.get_template("tasks/_table.html").render({"tasks": items})

    return HTMLResponse(html)
