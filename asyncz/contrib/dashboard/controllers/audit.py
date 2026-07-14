from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lilya.requests import Request
from lilya.responses import Response
from lilya.templating.controllers import TemplateController

from asyncz.contrib.dashboard.audit import get_audit_storage
from asyncz.contrib.dashboard.mixins import DashboardMixin


def _audit_filters(request: Request) -> dict[str, str]:
    params: Mapping[str, Any] = request.query_params
    return {
        "action": (params.get("action") or "").strip().lower(),
        "status": (params.get("status") or "").strip().lower(),
        "q": (params.get("q") or "").strip(),
        "limit": (params.get("limit") or "200").strip() or "200",
    }


def _limit(value: str) -> int:
    try:
        return max(1, min(int(value), 1000))
    except ValueError:
        return 200


def build_audit_context(request: Request) -> dict[str, Any]:
    filters = _audit_filters(request)
    storage = get_audit_storage()
    rows = storage.query(
        action=filters["action"] or None,
        status=filters["status"] or None,
        q=filters["q"] or None,
        limit=_limit(filters["limit"]),
    )
    return {
        "filters": filters,
        "rows": rows,
        "summary": storage.summary(),
    }


class AuditPageController(DashboardMixin, TemplateController):
    template_name: str = "audit/index.html"

    async def get(self, request: Request) -> Response:
        context = await self.get_context_data(
            request=request,
            title="Audit",
            page_header="Audit Trail",
            active_page="audit",
        )
        context.update(build_audit_context(request))
        return await self.render_template(request, context=context)
