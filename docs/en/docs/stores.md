# Stores

Stores persist scheduled tasks. The default store is in-memory, but Asyncz also ships with durable stores for local development and production deployments.

## Built-in stores

| Store | Plugin alias | Notes |
| ----- | ------------ | ----- |
| `MemoryStore` | `memory` | Default, process-local, non-persistent |
| `FileStore` | `file` | Local directory-based persistence and coordination |
| `MongoDBStore` | `mongodb` or `mongo` | Durable MongoDB-backed persistence |
| `RedisStore` | `redis` | Durable Redis-backed persistence |
| `SQLAlchemyStore` | `sqlalchemy` | Durable SQL-backed persistence |

## Store encryption

All built-in stores except `MemoryStore` support `ASYNCZ_STORE_ENCRYPTION_KEY`.

When it is set, Asyncz encrypts serialized task payloads before they are written to the store. This is strongly recommended for any store that can be modified by untrusted users or processes.

## `MemoryStore`

The default store. It is fast and simple, but it does not survive process restarts.

```python
from asyncz.stores.memory import MemoryStore
```

## `FileStore`

Stores each task as a file in a directory. This is useful for local multi-process coordination without introducing an external service.

```python
from asyncz.stores.file import FileStore
```

Key parameters:

- `directory`
- `suffix`
- `mode`
- `cleanup_directory`
- `pickle_protocol`

## `RedisStore`

```python
from asyncz.schedulers import AsyncIOScheduler
from asyncz.stores.redis import RedisStore

scheduler = AsyncIOScheduler(stores={"default": RedisStore()})
```

Key parameters:

- `database`
- `tasks_key`
- `run_times_key`
- `pickle_protocol`
- `host`
- `port`

## `MongoDBStore`

```python
from asyncz.schedulers import AsyncIOScheduler
from asyncz.stores.mongo import MongoDBStore

scheduler = AsyncIOScheduler(stores={"default": MongoDBStore()})
```

Key parameters:

- `database`
- `collection`
- `client`
- `pickle_protocol`
- Mongo client kwargs such as `host` and `port`

## `SQLAlchemyStore`

```python
from asyncz.schedulers import AsyncIOScheduler
from asyncz.stores.sqlalchemy import SQLAlchemyStore

scheduler = AsyncIOScheduler(
    stores={"default": SQLAlchemyStore(database="sqlite:///./asyncz.sqlite3")}
)
```

Key parameters:

- `database`
- `tablename`
- `pickle_protocol`
- extra kwargs forwarded to `sqlalchemy.create_engine()`

## Custom stores

If you need a different persistence backend, subclass `BaseStore` and implement the store contract.

```python
{!> ../../../docs_src/stores/custom.py !}
```
