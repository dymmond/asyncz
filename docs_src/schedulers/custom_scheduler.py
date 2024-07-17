from asyncz.schedulers.base import BaseScheduler
from asyncz.typing import Any


class MyCustomScheduler(BaseScheduler):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def start(self, paused: bool = False):
        # logic for the start
        ...

    def shutdown(self, wait: bool = True):
        # logic for the shutdown
        ...

    def wakeup(self):
        # logic for the wakeup
        ...

    def create_default_executor(self):
        # logic for your default executor
        ...
