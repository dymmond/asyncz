from __future__ import annotations

import click

_STORE_ALIASES = {
    "durable": "sqlalchemy",
    "sql": "sqlalchemy",
    "sqlite": "sqlalchemy",
    "sqlalchemy": "sqlalchemy",
    "memory": "memory",
}


def parse_store_option(spec: str) -> tuple[str, dict]:
    """
    Accepts things like:
      - "durable=sqlite:///file.db"
      - "sqlalchemy=sqlite:///file.db"
      - "memory"
    Returns (plugin_id, kwargs) suitable for scheduler.add_store(..., **kwargs).
    """
    if not spec:
        # default to in-memory store
        return "memory", {}

    if "=" in spec:
        kind, value = spec.split("=", 1)
        kind = kind.strip().lower()
        value = value.strip()
    else:
        kind, value = spec.strip().lower(), None

    plugin = _STORE_ALIASES.get(kind, kind)

    if plugin == "sqlalchemy":
        if not value:
            raise click.BadParameter(
                "SQLAlchemy store requires a database URL, e.g. durable=sqlite:///file.db"
            )
        # IMPORTANT: SQLAlchemyStore(database=...)
        return "sqlalchemy", {"database": value}

    if plugin == "memory":
        return "memory", {}

    raise click.BadParameter(
        f"Unknown store '{kind}'. Try one of: {', '.join(sorted(_STORE_ALIASES))}."
    )
