from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from lilya.requests import Request
from lilya.responses import HTMLResponse

from asyncz.contrib.dashboard.engine import templates
from asyncz.tasks.inspection import TaskInfo
from asyncz.triggers.cron import CronTrigger
from asyncz.triggers.date import DateTrigger
from asyncz.triggers.interval import IntervalTrigger

if TYPE_CHECKING:
    from asyncz.schedulers import AsyncIOScheduler


def serialize(task: Any) -> dict[str, Any]:
    """
    Convert a task or task snapshot into a dashboard-friendly dictionary.

    Args:
        task: A live Asyncz task or a ``TaskInfo`` snapshot.

    Returns:
        A normalized mapping with both machine-friendly values and a few
        presentation-oriented fields used by the task table templates.
    """
    info: TaskInfo = task if isinstance(task, TaskInfo) else task.snapshot()
    next_run_time = info.next_run_time
    next_run_time_text = (
        next_run_time.isoformat()
        if isinstance(next_run_time, datetime)
        else (next_run_time or None)
    )

    return {
        "id": info.id,
        "name": info.name or "",
        "trigger": info.trigger_name or "-",
        "trigger_alias": info.trigger_alias or "",
        "trigger_description": info.trigger_description or "-",
        "next_run_time": next_run_time_text,
        "next_run_time_datetime": info.next_run_time,
        "store": info.store_alias or "default",
        "executor": info.executor or "default",
        "callable_name": info.callable_name or "",
        "callable_reference": info.callable_reference or "",
        "state": info.schedule_state.value,
        "pending": info.pending,
        "paused": info.paused,
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
        if "T" in tv and " " in tv:
            head, tail = tv.rsplit(" ", 1)
            if len(tail) == 5 and tail[2] == ":" and tail.replace(":", "").isdigit():
                tv = f"{head}+{tail}"
        try:
            dt_obj: datetime = datetime.fromisoformat(tv)
        except Exception as e:
            raise ValueError(f"Invalid ISO datetime: {tv}") from e
        return DateTrigger(run_at=dt_obj)

    raise ValueError(f"Unsupported trigger type: {trigger_type}")


def _collect_messages(request: Request, context: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Collects flash messages from context and/or request.state._flash_messages (if any),
    returning a normalized list of {"level": str, "text": str}.
    """
    msgs: list[dict[str, Any]] = []

    # 1) From context
    ctx_msgs = context.get("messages") or []
    if isinstance(ctx_msgs, (list, tuple)):
        for m in ctx_msgs:
            if isinstance(m, dict) and "text" in m:
                level = str(m.get("level", "info"))
                msgs.append({"level": level, "text": str(m["text"])})
            elif hasattr(m, "text"):
                level = getattr(m, "level", "info")
                msgs.append({"level": str(level), "text": str(m.text)})

    # 2) From request.state (common pattern for add_message middleware)
    state_msgs = getattr(getattr(request, "state", None), "_flash_messages", None)
    if isinstance(state_msgs, (list, tuple)):
        for m in state_msgs:
            if isinstance(m, dict) and "text" in m:
                level = str(m.get("level", "info"))
                msgs.append({"level": level, "text": str(m["text"])})
    return msgs


def _render_messages_oob(request: Request, context: dict[str, Any]) -> str:
    """
    Renders an OOB (out-of-band) HTMX fragment with flash messages so that partial
    responses (like table reloads) can still update the top-of-page banner.

    Looks for `templates/partials/_messages_oob.html` first. If not found, falls back
    to an inline builder using Tailwind classes.
    """
    msgs = _collect_messages(request, context)
    if not msgs:
        # Return an empty OOB container to clear any previous banners
        return '<div id="flash-messages" hx-swap-oob="true"></div>'

    # Try to use a user-provided partial if it exists
    try:
        tpl = templates.get_template("partials/_messages_oob.html")
        # Ensure messages are available to the template
        return tpl.render({**context, "messages": msgs})
    except Exception:
        # Fallback: inline render
        parts: list[str] = [
            '<div id="flash-messages" hx-swap-oob="true">',
            '<div class="space-y-4 w-full">',
        ]
        for i, m in enumerate(msgs, start=1):
            level = (m.get("level") or "info").lower()
            if level == "success":
                color = "green"
                icon = "check-circle"
            elif level == "error":
                color = "red"
                icon = "x-circle"
            elif level == "warning":
                color = "yellow"
                icon = "alert-triangle"
            else:
                color = "blue"
                icon = "info"
            text = str(m.get("text", ""))
            parts.append(
                f"""
                  <div id="flash-{i}" class="relative flex items-start gap-3 p-4 bg-{color}-50
                  border-l-4 border-{color}-500 text-{color}-700 shadow transition-opacity duration-200">
                    <i data-lucide="{icon}" class="w-5 h-5 mt-1 flex-shrink-0"></i>
                    <div class="flex-1 leading-relaxed">{text}</div>
                    <button type="button" onclick="(function(id){{const el=document.getElementById(id); if(el){{el.classList.add('opacity-0'); setTimeout(()=>el.remove(),200);}}}})('flash-{i}');"
                      class="absolute top-5 right-6 text-xl font-bold leading-none text-{color}-700 hover:text-{color}-900 focus:outline-none"
                      aria-label="Dismiss">&times;</button>
                  </div>
                  """
            )
        parts.append("</div></div>")
        return "".join(parts)


def parse_task_filters(request: Request) -> dict[str, Any]:
    """
    Parse and normalize task-filter query parameters from a dashboard request.

    The returned mapping matches the scheduler's ``get_task_infos()`` API while
    also keeping the original form values needed by the templates.
    """

    params: Mapping[str, Any] = request.query_params
    q = (params.get("q") or "").strip() or None
    state = (params.get("state") or "").strip().lower() or None
    executor = (params.get("executor") or "").strip() or None
    trigger = (params.get("trigger") or "").strip() or None
    sort_by = (params.get("sort") or "next_run_time").strip() or "next_run_time"
    direction = (params.get("direction") or "asc").strip().lower() or "asc"
    descending = direction == "desc"
    return {
        "q": q,
        "schedule_state": state,
        "executor": executor,
        "trigger": trigger,
        "sort_by": sort_by,
        "descending": descending,
        "form": {
            "q": q or "",
            "state": state or "",
            "executor": executor or "",
            "trigger": trigger or "",
            "sort": sort_by,
            "direction": "desc" if descending else "asc",
        },
    }


def _build_task_query_suffix(filters: dict[str, str]) -> str:
    """
    Encode the active task filters into a reusable query-string suffix.

    The suffix is appended to HTMX endpoints and form actions so the task view
    keeps its current filters across partial refreshes and row/bulk actions.
    """

    query_values = {
        key: value
        for key, value in filters.items()
        if value
        and not (key == "sort" and value == "next_run_time")
        and not (key == "direction" and value == "asc")
    }
    query = urlencode(query_values)
    return f"?{query}" if query else ""


def build_task_dashboard_context(scheduler: AsyncIOScheduler, request: Request) -> dict[str, Any]:
    """
    Build the full task-list context used by both the full page and HTMX partials.

    This helper is the dashboard counterpart to ``scheduler.get_task_infos()``.
    It keeps task filters, sorting, summary counts, and available filter options
    in one place so the dashboard behaves consistently on first render and after
    any asynchronous updates.
    """

    parsed = parse_task_filters(request)
    filters = parsed["form"]
    all_infos = scheduler.get_task_infos()
    visible_infos = scheduler.get_task_infos(
        schedule_state=parsed["schedule_state"],
        executor=parsed["executor"],
        trigger=parsed["trigger"],
        q=parsed["q"],
        sort_by=parsed["sort_by"],
        descending=parsed["descending"],
    )
    available_executors = sorted(
        {info.executor or "default" for info in all_infos if info.executor}
    )
    available_triggers = sorted(
        {
            (info.trigger_alias or info.trigger_name or "").lower()
            for info in all_infos
            if info.trigger_alias or info.trigger_name
        }
    )
    return {
        "tasks": [serialize(info) for info in visible_infos],
        "filters": filters,
        "query_suffix": _build_task_query_suffix(filters),
        "available_executors": available_executors,
        "available_triggers": available_triggers,
        "visible_tasks": len(visible_infos),
        "total_tasks": len(all_infos),
        "scheduled_tasks": sum(
            1 for info in all_infos if info.schedule_state.value == "scheduled"
        ),
        "paused_tasks": sum(1 for info in all_infos if info.schedule_state.value == "paused"),
        "pending_tasks": sum(1 for info in all_infos if info.schedule_state.value == "pending"),
    }


async def render_table(scheduler: Any, request: Request, context: Any) -> HTMLResponse:
    """
    Render the task table partial for the current filter set.

    Args:
        scheduler: The active `AsyncIOScheduler` instance.
        request: The incoming Lilya request.

    Returns:
        HTMLResponse: An HTMX-friendly response containing:
          1) An out-of-band messages fragment to update the top banner, and
          2) The rendered `_table.html` template fragment.
    """
    context.update(build_task_dashboard_context(scheduler, request))
    table_html: str = templates.get_template("tasks/_table.html").render(context)

    # Also include the OOB messages so top-of-page banners update during partial swaps
    messages_oob_html: str = _render_messages_oob(request, context)

    return HTMLResponse(messages_oob_html + table_html)


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
