# Schedulers

Schedulers are the *thing* that makes all magic and binds everything together. You can see it as a
glue.

Usually the developer does not deal/handle the [stores](./stores.md), [executors](./executors.md)
or even [triggers](./triggers.md) manually, instead that is managed by the scheduler that acts
as an interface amongst them all.

Asyncz being dedicated to ASGI and asyncio brings the [AsyncIOScheduler](#asyncioscheduler)
out of the box and only supports this one natively but like everything in Asyncz, you can also
create your own [custom scheduler](#custom-scheduler) that does not necessarily need to be for
async. You can build your own scheduler for blocking/background applications.

In fact, Asyncz is used by [Esmerald](https://esmerald.dymmond.com) as internal scheduling system
and uses the [supported scheduler](./contrib/esmerald/scheduler.md) from Asyncz to perform its
tasks.

## AsyncIOScheduler

## Custom Scheduler
