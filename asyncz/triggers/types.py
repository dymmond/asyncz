from typing import Union

from asyncz.triggers.base import BaseTrigger
from asyncz.triggers.combination import AndTrigger, OrTrigger
from asyncz.triggers.cron.trigger import CronTrigger
from asyncz.triggers.date import DateTrigger
from asyncz.triggers.interval import IntervalTrigger

TriggerType = Union[BaseTrigger, DateTrigger, IntervalTrigger, OrTrigger, AndTrigger, CronTrigger]
