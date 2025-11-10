from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from lilya.requests import Request
from lilya.responses import HTMLResponse

from asyncz.contrib.dashboard.engine import templates
from asyncz.triggers.cron import CronTrigger
from asyncz.triggers.date import DateTrigger
from asyncz.triggers.interval import IntervalTrigger

if TYPE_CHECKING:
    from asyncz.executors.base import BaseExecutor
    from asyncz.schedulers import AsyncIOScheduler
    from asyncz.stores.base import BaseStore


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
        "trigger": str(trigger),
        "next_run_time": nrt_s,
        "store": getattr(task, "store_alias", None) or "default",
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


async def render_table(scheduler: Any, request: Request, context: Any) -> HTMLResponse:
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
    context.update({"tasks": items})
    html: str = templates.get_template("tasks/_table.html").render(context)

    return HTMLResponse(html)


def parse_ids_from_request_form(data: dict[str, Any]) -> list[str]:
    """
    Parses various forms of the "ids" payload received from HTML forms (e.g., HTMX bulk actions)
    into a de-duplicated, ordered list of string IDs.

    The function handles:
    - JSON-encoded list strings (e.g., '["a","b"]').
    - Comma-separated strings (e.g., 'a,b,c').
    - Python lists/tuples of strings/bytes.
    - Raw byte payloads.

    Args:
        data: The dictionary of form data received in the request body.

    Returns:
        A list of unique string IDs, preserving the order of first appearance.
    """
    raw: Any = data.get("ids")

    collected: list[str] = []

    # Normalize bytes → str
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode()
        except Exception:
            raw = str(raw)

    # List or tuple
    if isinstance(raw, (list, tuple)):
        for v in raw:
            if isinstance(v, (bytes, bytearray)):
                try:
                    v = v.decode()
                except Exception:
                    v = str(v)
            if isinstance(v, str):
                v = v.strip()
                # Check for nested JSON list
                if v.startswith("["):
                    try:
                        inner: Any = json.loads(v)
                        if isinstance(inner, list):
                            collected.extend([s for s in inner if isinstance(s, str)])
                            continue
                    except Exception:
                        pass
                # Treat as comma-separated string if not nested JSON list
                collected.extend([s for s in v.split(",") if s.strip()])
    elif isinstance(raw, str):
        s: str = raw.strip()
        if s.startswith("["):
            # Attempt to parse as JSON list
            try:
                val: Any = json.loads(s)
                if isinstance(val, list):
                    collected.extend([x for x in val if isinstance(x, str)])
                else:
                    collected.extend([p.strip() for p in s.split(",") if p.strip()])
            except Exception:
                # Fallback to comma-separated
                collected.extend([p.strip() for p in s.split(",") if p.strip()])
        elif s:
            # Simple comma-separated string
            collected.extend([p.strip() for p in s.split(",") if p.strip()])
    elif raw is not None:
        # Catch-all for non-string, non-list inputs
        s = str(raw)
        collected.extend([p.strip() for p in s.split(",") if p.strip()])

    # De-duplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for ident in collected:
        if ident not in seen:
            seen.add(ident)
            result.append(ident)
    return result


def safe_lookup_executor(scheduler: AsyncIOScheduler, alias: str | None) -> BaseExecutor | None:
    """
    Safely retrieves an executor instance from the scheduler, implementing graceful fallbacks.

    The search preference order is:
    1. The executor specified by `alias`.
    2. The executor set as `scheduler.default_executor`.
    3. The first configured executor instance found in `scheduler.executors`.

    Args:
        scheduler: The active `AsyncIOScheduler` instance.
        alias: The alias of the executor to look up.

    Returns:
        The `BaseExecutor` instance, or `None` if no executors are configured.
    """
    from asyncz.executors.base import BaseExecutor  # local import to avoid cycles

    # Candidate alias: Prefer given alias, fall back to configured default, then 'default'
    candidate: str = alias or getattr(scheduler, "default_executor", None) or "default"

    try:
        # 1. Try the candidate alias lookup
        return scheduler.lookup_executor(candidate)  # type: ignore[return-value]
    except KeyError:
        # 2. Fall back to the first configured executor if the lookup failed
        if getattr(scheduler, "executors", None):
            for _name, exec_obj in scheduler.executors.items():
                # Check if it's an instantiated executor object
                if isinstance(exec_obj, BaseExecutor):
                    return exec_obj
        # 3. No executors configured
        return None


def safe_lookup_store(
    scheduler: AsyncIOScheduler, alias: str | None = None, task_id: str | None = None
) -> BaseStore:
    """
    Safely retrieves a store instance from the scheduler without attempting to create a new one.

    The lookup order is:
    1. Exact alias match if provided and present in `scheduler.stores`.
    2. Probe stores to find the one that currently contains the given `task_id`.
    3. Fall back to the "default" store.
    4. Fall back to the first configured store available.

    Args:
        scheduler: The active `AsyncIOScheduler` instance.
        alias: The specific store alias to look up.
        task_id: An optional task ID used to probe stores for containment.

    Returns:
        The discovered `BaseStore` instance.

    Raises:
        KeyError: If the scheduler has no stores configured at all.
    """
    stores: dict[str, BaseStore] = getattr(scheduler, "stores", {}) or {}

    # 1. Direct alias hit
    if alias is not None and alias in stores:
        return stores[alias]

    # 2. Resolve by task id (probe stores; do NOT create new ones)
    if task_id:
        for _, store in stores.items():
            try:
                # get_task will raise TaskLookupError if not found
                store.get_task(task_id)
                return store
            except Exception:
                # Store either doesn't implement get_task or the task is not there
                continue

    # 3. Fallback to a configured default store
    if "default" in stores:
        return stores["default"]

    # 4. Fallback to the first store available
    for store in stores.values():
        return store

    # No stores at all
    raise KeyError("No stores are configured on the scheduler.")


def filter_items(items: list[dict[str, Any]], q: str | None) -> list[dict[str, Any]]:
    """
    Filters a list of task/job dictionaries by a simple, case-insensitive substring match.

    The search is performed across the **'id'**, **'name'**, **'store'**, and **'trigger'**
    fields of each dictionary. If the search query `q` is falsy (empty or None),
    the original list of items is returned unchanged.

    Args:
        items: A list of dictionaries (serialized task objects).
        q: The search query string.

    Returns:
        A new list containing only the items that match the search query, or the
        original list if no query was provided.
    """
    if not q:
        return items

    needle: str = q.strip().lower()
    filtered: list[dict[str, Any]] = []

    for it in items:
        # Normalize all checked fields to lower case strings for case-insensitive matching
        id_s: str = str(it.get("id", "")).lower()
        name_s: str = str(it.get("name", "")).lower()
        store_s: str = str(it.get("store", "")).lower()
        trigger_s: str = str(it.get("trigger", "")).lower()

        if needle in id_s or needle in name_s or needle in store_s or needle in trigger_s:
            filtered.append(it)

    return filtered
