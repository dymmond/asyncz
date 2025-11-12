from __future__ import annotations

from collections.abc import Iterable, Mapping
from functools import lru_cache
from typing import Any

from lilya.requests import Request
from lilya.responses import Response
from lilya.templating.controllers import TemplateController

from asyncz.contrib.dashboard.logs.storage import LogStorage, MemoryLogStorage
from asyncz.contrib.dashboard.mixins import DashboardMixin

_storage: MemoryLogStorage | None = None


@lru_cache
def get_log_storage(storage: LogStorage | None = None) -> LogStorage:
    """
    Retrieves the currently configured log storage instance.

    This function serves as the central access point for all components needing to read or write logs.

    Returns:
        LogStorage: The active log storage object (defaults to `MemoryLogStorage`).
    """
    return storage or MemoryLogStorage(maxlen=20_000)


def append_log(entry: dict) -> None:
    get_log_storage().append(entry)  # type: ignore


def query_logs(
    *, task_id: str | None = None, level: str | None = None, q: str | None = None
) -> Iterable[dict]:
    # delegate to your storage’s query/filter API
    return get_log_storage().query(task_id=task_id, level=level, q=q)  # type: ignore


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
        context: dict[str, Any] = await self.get_context_data(request=request)
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

        storage: LogStorage = get_log_storage()
        params: Mapping[str, Any] = request.query_params

        # Extract and type-hint query parameters
        task_id: str | None = params.get("task_id")
        level: str | None = params.get("level")
        q: str | None = params.get("q")

        # Safely parse limit, defaulting to 200
        limit: int
        try:
            limit = int(params.get("limit", "200") or 200)
        except ValueError:
            limit = 200

        # Query the storage
        # The storage.query() method is expected to return a filtered, ordered list of log records
        rows: list[Any] = list(storage.query(task_id=task_id, level=level, q=q, limit=limit))

        context.update({"rows": rows})
        return await self.render_template(request, context=context)
