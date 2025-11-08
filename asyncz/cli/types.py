from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from asyncz.triggers.base import BaseTrigger
from asyncz.triggers.cron import CronTrigger


def parse_interval(text: str) -> float:
    """
    Parses a human-readable duration string into total seconds.

    The format must be a number followed by a unit (s, m, or h), case-insensitive.
    Example formats: '10s', '5m', '2h'.

    Args:
        text: The input duration string.

    Returns:
        The duration converted into total seconds (float).

    Raises:
        ValueError: If the interval string is in an invalid format.
    """
    # Regex breakdown: (?i) case-insensitive, (\d+) one or more digits (value),
    # \s* optional whitespace, ([smh]) unit.
    m: re.Match[str] | None = re.fullmatch(r"(?i)(\d+)\s*([smh])", text.strip())

    if not m:
        raise ValueError("Invalid interval, use Ns/Nm/Nh (e.g., 10s, 5m, 2h)")

    value: int = int(m.group(1))
    unit: Literal["s", "m", "h"] = m.group(2).lower()  # type: ignore[assignment]

    # Mapping unit to multiplier
    mult: dict[str, int] = {"s": 1, "m": 60, "h": 3600}

    return float(value * mult[unit])


def parse_trigger(*, cron: str | None, interval: str | None, at: str | None) -> BaseTrigger:
    """
    Parses mutually exclusive job scheduling arguments into the appropriate Asyncz trigger object.

    Exactly one of the three arguments must be provided.

    Args:
        cron: A cron expression string (e.g., '0 0 * * *').
        interval: A human-readable duration string (e.g., '10m', '2h').
        at: An ISO 8601 formatted datetime string indicating a single run time.

    Returns:
        An instantiated subclass of `BaseTrigger` (CronTrigger, IntervalTrigger, or DateTrigger).

    Raises:
        ValueError: If the input specifies zero or more than one trigger type.
    """
    # Ensure exactly one argument is provided
    if sum(bool(x) for x in (cron, interval, at)) != 1:
        raise ValueError("Specify exactly one of --cron, --interval, or --at")

    if cron:
        return CronTrigger.from_crontab(cron)

    if interval:
        # IntervalTrigger
        seconds: float = parse_interval(interval)
        from asyncz.triggers.interval import IntervalTrigger

        return IntervalTrigger(seconds=int(seconds))

    # DateTrigger
    when: dt.datetime = dt.datetime.fromisoformat(at)  # type: ignore[arg-type]
    from asyncz.triggers.date import DateTrigger

    return DateTrigger(run_date=when)
