from typing import Any

from lilya.requests import Request

from asyncz import monkay
from asyncz.contrib.dashboard.config import get_effective_prefix
from asyncz.contrib.dashboard.engine import templates
from asyncz.contrib.dashboard.messages import get_messages


def default_context(request: Request) -> dict:
    context = {}
    effective_prefix = get_effective_prefix(request)
    context.update(
        {
            "title": monkay.settings.dashboard_config.title,
            "header_text": monkay.settings.dashboard_config.header_title,
            "favicon": monkay.settings.dashboard_config.favicon,
            "url_prefix": effective_prefix,
            "sidebar_bg_colour": "#f06824",
            "messages": get_messages(request),
        }
    )
    return context


class DashboardMixin:
    templates = templates

    async def get_context_data(self, request: Request, **kwargs: Any) -> dict:
        context = default_context(request)
        return context
