---
hide:
  - navigation
---

# Asyncz CLI

This is the official command-line client for Asyncz, a fast, lightweight task scheduler for Python applications.
It's designed for two modes:

- **Standalone**: manage jobs directly from the CLI using in-memory or persistent stores (SQLite, Redis, etc.).
- **Integrated**: let your framework/app (Ravyn, Lilya, FastAPI/Starlette, or anything) fully own the scheduler and jobs, while the CLI "talks" to your scheduler via a single bootstrap entry point.

The CLI is great for local dev, CI/CD, platform ops, and "Day-2"operations (`pause`/`resume`/`run`/`remove` jobs) without writing any code.

## Installation

```bash
pip install asyncz
```

You'll get the `asyncz` command on your PATH.

## What is this client?

- A single binary/entry point (`asyncz`) that can:
    - Start a scheduler (`start`)
    - Add tasks (`add`)
    - List tasks (`list`)
    - Trigger tasks now (`run`)
    - Pause/resume tasks (`pause`, `resume`)
    - Remove tasks (`remove`)
- It can run jobs from a Python module or from a YAML/JSON config, and it can also defer everything to your
application via a bootstrap class that returns a ready-to-run `AsyncIOScheduler`.

## Why & when to use it

- **Local development**:
    - quickly spin up a scheduler;
    - add a test job;
    - inspect the next run time; pause/resume while debugging.
- **Operations & SRE**:
    - modify job schedules in production without deploying code;
    - run compensating jobs immediately;
    - temporarily pause noisy/expensive jobs.
- **Framework integration**:
    - keep your framework's configuration and lifecycle (Ravyn/Lilya/FastAPI/Starlette) while letting the CLI manipulate the same scheduler instance.
- **CI/CD**:
    - seed initial jobs, verify scheduler connectivity to persistent stores, or smoke-test job registration via CLI.


## Advantages

- **Zero boilerplate**: everything is available as simple CLI commands.
- **Flexible sources**: jobs from Python modules or declarative configs.
- **Persistent or ephemeral**: wire persistent stores (e.g., SQLite/Redis) for durable schedules, or use in-memory for quick tests.
- **App-owned integration**: a tiny bootstrap contract lets any framework expose its scheduler so the CLI can operate on it.
- **Safe ops controls**: pause/resume/run/remove without touching your application code.

## Quick start (standalone)

Start a scheduler (no watch, no standalone mode)

```bash
asyncz start --store durable=sqlite:///scheduler.db --executor default=asyncio
```

This starts the scheduler, then cleanly exits (useful in CI to validate config).

### Add a job

```bash
asyncz add myapp.tasks:cleanup \
  --name nightly-cleanup \
  --cron "0 2 * * *" \
  --store durable=sqlite:///scheduler.db
```

### List jobs

```bash
asyncz list --store durable=sqlite:///scheduler.db
# or JSON for scripting:
asyncz list --json --store durable=sqlite:///scheduler.db
```

### Run now / Pause / Resume / Remove

```bash
asyncz run    <job_id> --store durable=sqlite:///scheduler.db
asyncz pause  <job_id> --store durable=sqlite:///scheduler.db
asyncz resume <job_id> --store durable=sqlite:///scheduler.db
asyncz remove <job_id> --store durable=sqlite:///scheduler.db
```

!!! Tip
    `--store` is alias=URL (repeatable). The first alias becomes the default write target for add (e.g., durable=sqlite:///…).

## Command reference

### start

Start a scheduler. Optionally load jobs from a module or config. Optional hot-reload loop.

```bash
asyncz start \
  [--module "pkg.jobs:registry"] \
  [--config ./jobs.yml] \
  [--timezone Europe/Zurich] \
  [--store durable=sqlite:///scheduler.db] \
  [--executor default=asyncio] \
  [--standalone] \
  [--watch] [--watch-interval 1.0]
```

- `--module`: Python path to a registry (e.g., `pkg.jobs:registry`) that adds/registers jobs.
- `--config`: YAML/JSON file with job definitions.
- `--standalone`: keep the process running until Ctrl-C (use for dev/service mode).
- `--watch`: hot-reload when module/config files change.

### add

Add a new job with a `cron`/`interval`/`date trigger`.

```bash
asyncz add pkg.module:callable \
  --name my-job \
  --cron "*/5 * * * *" \
  --args '["a", 123]' \
  --kwargs '{"flag": true}' \
  --store durable=sqlite:///scheduler.db
```

Mutually exclusive: `--cron` | `--interval '10s|5m|2h'` | `--at '2026-01-01T10:00:00'`.

### list

List currently scheduled jobs.

```bash
asyncz list [--json] --store durable=sqlite:///scheduler.db
```

### run

Force a job to execute immediately and advance its schedule.

```bash
asyncz run <job_id> --store durable=sqlite:///scheduler.db
```

### pause / resume / remove

```bash
asyncz pause  <job_id> --store durable=sqlite:///scheduler.db
asyncz resume <job_id> --store durable=sqlite:///scheduler.db
asyncz remove <job_id> --store durable=sqlite:///scheduler.db
```

## Real-world examples

1) **Nightly data warehouse maintenance**

- Add a 02:00 cron job to vacuum/optimize tables:

```bash
asyncz add dw.tasks:vacuum --name dw-vacuum --cron "0 2 * * *" \
  --store durable=sqlite:///scheduler.db
```

- Pause during backfills:

```bash
asyncz pause <job_id> --store durable=sqlite:///scheduler.db
```

- Resume after backfill completes:

```bash
asyncz resume <job_id> --store durable=sqlite:///scheduler.db
```

2) **On-demand reporting**

- Add a periodic report:

```bash
asyncz add reports.weekly:send --name sales-weekly --interval "1w" \
  --store durable=sqlite:///scheduler.db
```

- Trigger now for a one-off:

```bash
asyncz run <job_id> --store durable=sqlite:///scheduler.db
```

3) **Blue/Green ops**

- Maintain jobs in a persistent store; on new deployments:
- Start once in CI to validate config connectivity:

```bash
asyncz start --store durable=sqlite:///scheduler.db --executor default=asyncio
```

- No jobs lost: store state survives blue/green swaps.


## Integration via bootstrap (Ravyn, Lilya, FastAPI, Starlette, Litestar ...)

Sometimes your application already owns the scheduler and task registration.
You don't want the CLI to rebuild anything, you want it to "attach" to your existing scheduler.

That's exactly what `--bootstrap` does:

```bash
asyncz start --bootstrap "yourpkg.somewhere:AsynczSpec"
```

### The contract (tiny!)

Provide a class/object/callable that yields an `AsyncIOScheduler`:

- Class with a `get_scheduler(self) -> AsyncIOScheduler`
- Object with a `get_scheduler()` method
- Callable returning `AsyncIOScheduler`

The CLI imports this target and uses the scheduler you return, ignoring other flags like
`--store`, `--module`, `--config`, etc. (It will start the scheduler if it's not already running.)

### Example: Ravyn

Ravyn already ships an `AsynczConfig` that constructs and wires the scheduler as handler. Your bootstrap class can be:

```python
from asyncz.schedulers import AsyncIOScheduler
from ravyn.contrib.schedulers.asyncz.config import AsynczConfig

class AsynczSpec:
    def __init__(self) -> None:
        # configure via Ravyn's settings if needed
        self.config = AsynczConfig()  # tasks/timezone/configurations from Ravyn
    def get_scheduler(self) -> AsyncIOScheduler:
        return self.config.handler
```

**Run**:

```bash
asyncz start --bootstrap "ravyn.contrib.asyncz:AsynczSpec"
```

Now you can `add`/`list`/`run`/`pause`/`resume`/`remove` against the application-owned scheduler:

```bash
asyncz add myproj.jobs:send_report \
  --name send-report --interval "10m" \
  --bootstrap ravyn.contrib.asyncz:AsynczSpec

asyncz list --bootstrap ravyn.contrib.asyncz:AsynczSpec
asyncz run  <job_id> --bootstrap ravyn.contrib.asyncz:AsynczSpec
asyncz pause <job_id> --bootstrap ravyn.contrib.asyncz:AsynczSpec
```

Under the hood, Asyncz caches the scheduler per bootstrap path in-process so subsequent commands
see the same in-memory state during a test run or REPL session.

### Example: Lilya

```python
from asyncz.schedulers import AsyncIOScheduler

class AsynczSpec:
    def __init__(self) -> None:
        self.sched = AsyncIOScheduler(stores={"default": {"type": "memory"}})
        # Register Lilya-powered jobs here (or elsewhere in app init)
    def get_scheduler(self) -> AsyncIOScheduler:
        return self.sched
```

```bash
asyncz list --bootstrap "lilya.contrib.asyncz:AsynczSpec"
```

### Example: FastAPI / Starlette

If you're wiring a scheduler in an ASGI app:

```python
from asyncz.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(stores={"default": {"type": "memory"}})

def get_scheduler():
    # If your app starts/stops the scheduler, that's fine; the CLI will
    # attempt a start (and safely ignore "already running" errors).
    return scheduler
```

Then simply pass the location of the callable into the cli.

```bash
asyncz add myapp.jobs:tick --interval "5s" --bootstrap "myapp.bootstrap:get_scheduler"
```

## Choosing between standalone and bootstrap

Use standalone when:

- You want the CLI to create/configure the scheduler from flags.
- You want to manage stores directly from the CLI.
- You're seeding or manipulating a persistent store out-of-band.

Use bootstrap when:

- Your framework/app already owns the scheduler and jobs.
- You want the CLI to operate on that exact scheduler instance.
- You prefer a single source of truth for configuration (the app).


## Tips & troubleshooting

- When using `--bootstrap`, `--store`, `--module`, `--config`, `--watch` are ignored because your app is the source of truth.
- If you see no jobs with list in bootstrap mode, ensure your bootstrap returns the same scheduler
instance the app uses (or let Asyncz's in-process cache help during tests).
- Cron parsing uses standard 5-field crontab strings (`*/5 * * * *`).
- `--args`/`--kwargs` must be valid JSON; the CLI passes them to your callable.

## Minimal checklist to integrate your framework

1. Create a class/object/callable that returns an `AsyncIOScheduler`.
2. Register your jobs on that scheduler (in app code).
3. Run any CLI command with `--bootstrap "<your.module:Target>"`.

That's it. You now have a proper separation between app-owned config and ops-level controls—with the ease of a single CLI.
