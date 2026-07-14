from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lilya.requests import Request
from lilya.responses import Response
from lilya.templating.controllers import TemplateController

from asyncz.contrib.dashboard.events import EVENT_NAMES, get_scheduler_event_storage
from asyncz.contrib.dashboard.mixins import DashboardMixin


def _event_filters(request: Request) -> dict[str, str]:
    params: Mapping[str, Any] = request.query_params
    return {
        "category": (params.get("category") or "").strip().lower(),
        "name": (params.get("name") or "").strip().lower(),
        "task_id": (params.get("task_id") or "").strip(),
        "q": (params.get("q") or "").strip(),
        "limit": (params.get("limit") or "200").strip() or "200",
    }


def _limit(value: str) -> int:
    try:
        return max(1, min(int(value), 1000))
    except ValueError:
        return 200


def build_events_context(request: Request) -> dict[str, Any]:
    filters = _event_filters(request)
    storage = get_scheduler_event_storage()
    rows = storage.query(
        category=filters["category"] or None,
        name=filters["name"] or None,
        task_id=filters["task_id"] or None,
        q=filters["q"] or None,
        limit=_limit(filters["limit"]),
    )
    return {
        "filters": filters,
        "rows": rows,
        "summary": storage.summary(),
        "event_names": sorted(set(EVENT_NAMES.values())),
        "categories": ["scheduler", "store", "executor", "task"],
    }


class EventsPageController(DashboardMixin, TemplateController):
    template_name: str = "events/index.html"

    async def get(self, request: Request) -> Response:
        context = await self.get_context_data(
            request=request,
            title="Events",
            page_header="Scheduler Events",
            active_page="events",
        )
        context.update(build_events_context(request))
        return await self.render_template(request, context=context)
