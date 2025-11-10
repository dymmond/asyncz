# Asyncz Settings

Asyncz provides a flexible configuration system inspired by Lilya's settings model.
It allows you to define, customize, and override configuration parameters globally for your Asyncz-based project
or scheduler.

All default settings are defined in:

```python
asyncz.conf.global_settings.Settings
```

You can override them via environment variables or through a custom settings module.

## Default Settings Module

The default settings class is:

```python
from asyncz.conf.global_settings import Settings
```

Asyncz automatically loads this class at startup as the global configuration object.

You can access it anywhere as:

```python
from asyncz import settings

print(settings.debug)   # → False by default
print(settings.version) # → "x.y.z"
```

or access the class itself:

```python
from asyncz import Settings
```

## How It Works

The settings system is environment-aware and dynamic:

1. When you import `asyncz.settings`, Asyncz looks for an environment variable called:

   ```
   ASYNCZ_SETTINGS_MODULE
   ```

2. If found, Asyncz imports the specified module (e.g. `myproject.conf.settings`) and uses its attributes to
override the default ones from `asyncz.conf.global_settings.Settings`.
3. If not found, Asyncz falls back to its built-in defaults.

This design mirrors Ravyn's/AsyncMQ's/Lilya's configuration model, ensuring your Asyncz instance always has a
consistent, globally accessible settings object.

## Example: Custom Project Settings

Assume the project structure is:

```
myproject/
├── app.py
└── conf/
    └── settings.py
```

### 1. Create your custom settings module

```python
# myproject/conf/settings.py
from asyncz.conf.global_settings import Settings as BaseSettings

class Settings(BaseSettings):
    debug = True
    scheduler_store = "redis://localhost:6379/0"
```

### 2. Export the module path

In your shell (or `.env` file):

```bash
export ASYNCZ_SETTINGS_MODULE="myproject.conf.settings.Settings"
```

### 3. Use it in your code

```python
from asyncz import settings

print(settings.debug)  # True
print(settings.scheduler_store)  # "redis://localhost:6379/0"
```

## Available Settings

### debug

- **Type:** `bool`
- **Default:** `False`
- **Description:** Enables debug mode if `True`. May activate additional logging, detailed error reporting,
and other debugging features.

### version

- **Type:** `str`
- **Default:** `asyncz.__version__`
- **Description:**
  Stores the current version string of the Asyncz library for informational purposes.

### dashboard_config

- **Type:** `property → DashboardConfig`
- **Description:** Dynamically imports and returns the configuration object used by the
Asyncz dashboard (`asyncz.contrib.dashboard.config.DashboardConfig`). Example usage:

    ```python
    from asyncz import settings

    dash = settings.dashboard_config
    print(dash.dashboard_url_prefix)
    ```

## Environment Variables

You can override any setting using environment variables.

Each setting key is automatically uppercased when resolving from the environment.

For example:

```bash
export DEBUG=true
export VERSION="dev"
```

will override:

```python
settings.debug == True
settings.version == "dev"
```

Boolean environment values support: `"true"`, `"1"`, `"yes"`, `"on"`, `"y"` (case-insensitive).

## Advanced: Custom Setting Classes

You can also extend `BaseSettings` to build your own configuration system.

```python
from asyncz.conf.global_settings import BaseSettings

class CustomSettings(BaseSettings):
    name: str = "Scheduler"
    enabled: bool = True
    retries: int = 3
```

This class automatically:

- Loads environment variables (`NAME`, `ENABLED`, `RETRIES`);
- Converts them to the proper type;
- Supports `dict()` and `tuple()` exports.

## Accessing Settings Programmatically

| Method               | Description                          |
|----------------------|------------------------------------|
| `settings.dict()`    | Returns all settings as a dictionary |
| `settings.tuple()`   | Returns all settings as a list of key/value tuples |
| `settings.dashboard_config` | Returns dashboard configuration |
| `settings.debug`     | Direct attribute access             |
| `settings.post_init()` | Hook for subclasses after initialization |

Example:

```python
from asyncz import settings

print(settings.dict(upper=True))
# {'DEBUG': False, 'VERSION': '1.0.0', ...}
```

## Integration Example

```python
from asyncz import settings
from asyncz.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(
    stores={"default": {"type": "memory"}},
    timezone=settings.dashboard_config.timezone
)

scheduler.start()
```

## Summary

| Feature             | Description                                  |
|---------------------|----------------------------------------------|
| File                | `asyncz.conf.global_settings`                |
| Env var override    | `ASYNCZ_SETTINGS_MODULE`                      |
| Access              | `from asyncz import settings`                 |
| Custom extension    | Inherit from `BaseSettings`                    |
| Automatic casting   | `bool`, `int`, `str`, `Union`, etc.           |
| Dashboard config    | `settings.dashboard_config` provides dashboard settings |
