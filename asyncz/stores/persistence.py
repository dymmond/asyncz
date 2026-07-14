from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TASK_STATE_ENTITY = "task_state"
TASK_STATE_ENVELOPE_VERSION = 1


@dataclass(frozen=True)
class TaskStateEnvelope:
    """
    Versioned persistence envelope for serialized task state.

    Stores own when and where bytes are persisted. The envelope records the
    selected Shape identity and persistence version while preserving Asyncz's
    native task state payload for backward-compatible pickle restoration.
    """

    entity: str
    version: int
    shape: str
    payload: Any
