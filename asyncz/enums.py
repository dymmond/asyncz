from enum import Enum, IntEnum


class SchedulerState(IntEnum):
    STATE_STOPPED = 0
    STATE_RUNNING = 1
    STATE_PAUSED = 2


class PluginInstance(str, Enum):
    EXECUTOR = "executor"
    STORE = "store"


class TaskScheduleState(str, Enum):
    """
    Stable task lifecycle labels used for task inspection APIs and UI surfaces.

    Asyncz tasks can be observed in three scheduler-facing states:

    - ``pending``: the task exists only in the scheduler's pending queue and has
      not been committed to a started store yet
    - ``paused``: the task is stored but has no ``next_run_time``
    - ``scheduled``: the task has an upcoming ``next_run_time``
    """

    PENDING = "pending"
    PAUSED = "paused"
    SCHEDULED = "scheduled"
