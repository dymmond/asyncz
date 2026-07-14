from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lilya.requests import Request
from lilya.responses import Response
from lilya.templating.controllers import TemplateController

from asyncz.contrib.dashboard.controllers.logs import get_log_storage
from asyncz.contrib.dashboard.engine import templates
from asyncz.contrib.dashboard.history import (
    get_run_history_storage,
    logs_for_run,
)
from asyncz.contrib.dashboard.mixins import DashboardMixin


def _history_filters(request: Request) -> dict[str, str]:
    params: Mapping[str, Any] = request.query_params
    return {
        "task_id": (params.get("task_id") or "").strip(),
        "status": (params.get("status") or "").strip().lower(),
        "source": (params.get("source") or "").strip().lower(),
        "q": (params.get("q") or "").strip(),
        "limit": (params.get("limit") or "200").strip() or "200",
    }


def _limit(value: str) -> int:
    try:
        return max(1, min(int(value), 1000))
    except ValueError:
        return 200


def build_history_context(request: Request) -> dict[str, Any]:
    filters = _history_filters(request)
    storage = get_run_history_storage()
    rows = storage.query(
        task_id=filters["task_id"] or None,
        status=filters["status"] or None,
        source=filters["source"] or None,
        q=filters["q"] or None,
        limit=_limit(filters["limit"]),
    )
    return {
        "filters": filters,
        "rows": rows,
        "summary": storage.summary(),
    }


class HistoryPageController(DashboardMixin, TemplateController):
    template_name: str = "history/index.html"

    async def get(self, request: Request) -> Response:
        context = await self.get_context_data(
            request=request,
            title="History",
            page_header="Run History",
            active_page="history",
        )
        context.update(build_history_context(request))
        return await self.render_template(request, context=context)


class HistoryTablePartialController(DashboardMixin, TemplateController):
    template_name: str = "history/partials/table.html"

    async def get(self, request: Request) -> Response:
        context = await self.get_context_data(request=request)
        context.update(build_history_context(request))
        return await self.render_template(request, context=context)


class HistoryDetailController(DashboardMixin, TemplateController):
    template_name: str = "history/detail.html"

    async def get(self, request: Request) -> Response:
        run_id = request.path_params["run_id"]
        storage = get_run_history_storage()
        record = storage.get(run_id)

        context = await self.get_context_data(
            request=request,
            title="Run Detail",
            page_header="Run Detail",
            active_page="history",
            record=record,
            rows=[],
        )

        if record is None:
            return templates.get_template_response(
                request,
                self.template_name,
                context=context,
                status_code=404,
            )

        context["rows"] = logs_for_run(record, get_log_storage())
        return await self.render_template(request, context=context)
