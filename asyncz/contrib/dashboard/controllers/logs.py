from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from lilya.requests import Request
from lilya.responses import Response
from lilya.templating.controllers import TemplateController

from asyncz.contrib.dashboard.logs.storage import LogStorage, MemoryLogStorage
from asyncz.contrib.dashboard.mixins import DashboardMixin

_storage: LogStorage | None = None


def get_log_storage(storage: LogStorage | None = None) -> LogStorage:
    """
    Retrieves the currently configured log storage instance.

    This function serves as the central access point for all components needing to read or write logs.

    Returns:
        LogStorage: The active log storage object (defaults to `MemoryLogStorage`).
    """
    global _storage

    if storage is not None:
        _storage = storage
    elif _storage is None:
        _storage = MemoryLogStorage(maxlen=20_000)

    return _storage


def append_log(entry: dict) -> None:
    get_log_storage().append(entry)  # type: ignore


def query_logs(
    *,
    task_id: str | None = None,
    run_id: str | None = None,
    level: str | None = None,
    q: str | None = None,
) -> Iterable[dict]:
    # delegate to your storage’s query/filter API
    return get_log_storage().query(task_id=task_id, run_id=run_id, level=level, q=q)  # type: ignore


def _log_filters(request: Request) -> dict[str, str]:
    params: Mapping[str, Any] = request.query_params
    return {
        "task_id": (params.get("task_id") or "").strip(),
        "run_id": (params.get("run_id") or "").strip(),
        "level": (params.get("level") or "").strip().upper(),
        "q": (params.get("q") or "").strip(),
        "limit": (params.get("limit") or "200").strip() or "200",
    }


def _limit(value: str) -> int:
    try:
        return max(1, min(int(value), 1000))
    except ValueError:
        return 200


def build_log_context(request: Request) -> dict[str, Any]:
    filters = _log_filters(request)
    storage = get_log_storage()
    rows = list(
        storage.query(
            task_id=filters["task_id"] or None,
            run_id=filters["run_id"] or None,
            level=filters["level"] or None,
            q=filters["q"] or None,
            limit=_limit(filters["limit"]),
        )
    )
    return {"filters": filters, "rows": rows}


class LogsPageController(DashboardMixin, TemplateController):
    """
    Controller for rendering the full Logs management dashboard page.

    This page includes the necessary filtering controls and acts as the container
    for the dynamic log table loaded separately via HTMX.
    """

    template_name: str = "logs/index.html"

    async def get(self, request: Request) -> Response:
        """
        Handles the GET request and renders the main log page template.

        Args:
            request: The incoming Lilya Request object.

        Returns:
            Response: The rendered HTML response for the log index page.
        """
        context: dict[str, Any] = await self.get_context_data(
            request=request,
            title="Logs",
            page_header="Logs",
            active_page="logs",
        )
        context.update(build_log_context(request))
        return await self.render_template(request, context=context)


class LogsTablePartialController(DashboardMixin, TemplateController):
    """
    Controller for rendering only the dynamic table rows of log entries.

    This endpoint is designed as an HTMX target for fast, partial updates and supports
    filtering the log data based on query parameters.
    """

    template_name: str = "logs/partials/table.html"

    async def get(self, request: Request) -> Response:
        """
        Handles the GET request, queries the log storage based on filters, and renders
        the partial HTML table.

        Args:
            request: The incoming Lilya Request object. Query parameters are used for filtering.

        Returns:
            Response: The rendered HTML response fragment containing log rows.
        """
        context: dict[str, Any] = await self.get_context_data(request=request)

        context.update(build_log_context(request))
        return await self.render_template(request, context=context)
