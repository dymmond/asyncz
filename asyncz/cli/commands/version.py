from __future__ import annotations

import json
from typing import Annotated

from sayer import Option, command, info

from asyncz import __version__


@command(name="version")
def version(
    as_json: Annotated[bool, Option(False, "--json", help="Output as JSON")],
) -> dict[str, str] | None:
    """Print the installed Asyncz version."""

    payload = {"version": __version__}
    if as_json:
        print(json.dumps(payload))
        return payload

    info(__version__)
    return None
