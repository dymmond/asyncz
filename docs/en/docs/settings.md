# Asyncz Settings

Asyncz exposes a small global settings object through `asyncz.settings`. The default implementation lives in `asyncz.conf.global_settings.Settings`.

## Built-in settings

`Settings` currently defines:

- `debug: bool = False`
- `version: str = asyncz.__version__`
- `secret_key: str | None = None`
- `dashboard_config`: a property that builds `asyncz.contrib.dashboard.config.DashboardConfig`

## Loading a custom settings class

Point `ASYNCZ_SETTINGS_MODULE` at a class path:

```bash
export ASYNCZ_SETTINGS_MODULE="myproject.conf.settings.Settings"
```

Example:

```python
from asyncz.conf.global_settings import Settings as BaseSettings


class Settings(BaseSettings):
    debug = True
    secret_key = "development-only-secret"
```

## Accessing settings

```python
from asyncz import settings

print(settings.debug)
print(settings.version)
print(settings.dashboard_config.dashboard_url_prefix)
```

You can also import the settings class itself:

```python
from asyncz import Settings
```

## Export helpers

`BaseSettings` includes convenience helpers:

- `settings.dict(...)`
- `settings.tuple(...)`

Both support `exclude_none`, `upper`, `exclude`, and `include_properties`.

## Dashboard configuration

`settings.dashboard_config` returns an `asyncz.contrib.dashboard.config.DashboardConfig` instance. That object controls dashboard-specific behavior such as:

- `dashboard_url_prefix`
- `title`
- `header_title`
- `description`
- session middleware settings and cookie configuration

If `secret_key` is set on the root settings object, it is forwarded into `DashboardConfig`.
