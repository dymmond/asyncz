# Executors

Have you ever wondered what handles the tasks? Well, those are the executors and since Asyncz is
designed to be more focused on ASGI and asyncio that also means it only provides the
[AsyncIOExecutor](#asyncioexecutor) and the
[ThreadPoolExecutor](#threadpoolexecutor)/[ProcessPoolExecutor](#processpoolexecutor) out of the
box but you can also create your own [custom executor](#custom-executor) if you which as well.

When a task is done, it sends a notification to the scheduler informing that the task is done which
triggers the appropriate event.

## AsyncIOExecutor

## ThreadPoolExecutor

## ProcessPoolExecutor

## Custom executor
