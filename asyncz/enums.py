from enum import Enum, IntEnum


class SchedulerState(IntEnum):
    STATE_STOPPED = 0
    STATE_RUNNING = 1
    STATE_PAUSED = 2


class PluginInstance(str, Enum):
    EXECUTOR = "executor"
    STORE = "store"
