from enum import Enum


class SchedulerState(Enum):
    STATE_STOPPED = 0
    STATE_RUNNING = 1
    STATE_PAUSED = 2


class PluginInstance(Enum):
    EXECUTOR = "executor"
    STORE = "store"
