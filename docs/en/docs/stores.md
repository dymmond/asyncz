# Stores

In simple terms, the stores are places where, as the name suggests, stores the scheduled tasks.
Asyncz has a `default` store wich is a [MemoryStore](#memorystore) but also brings an integration
with three major ones, [Redis](#redisstore), [SQLAlchemy](#sqlalchemystore) and [MongoDB](#mongodbstore).

Besides the default memory store, the tasks are not store in memory but in the corresponding desired
store.

You are also capable of building your own store if you which, for instance to integrate SQLAlchemy
or Tortoise ORM or anything else. Check out the [custom store](#custom-store) section for more
information.

All the states are serialized and reversed using pydantic objects, so keep that in mind when
creating a [custom store](#custom-store).


## Store Encryption

You should use store encryption for security reasons.

All standard stores except MemoryStore support the environment variable `ASYNCZ_STORE_ENCRYPTION_KEY`.
If set and non-empty the hash of the value is used for AESGCM encrypting the elements before sending them
to the store.
This way store entries are encrypted and authentificated so there is no security hole.
This is highly recommended! Because if someone can inject store entries he can execute code.


## MemoryStore

This is the default store when using Asyncz and probably the one you will be using when running
stateless tasks or tasks that do not require some sort of cache.

**Store Alias** - `memory`

```python
from asyncz.stores.memory import MemoryStore
```

## FileStore

This is also a basic store which is always available. It supports the task synchronization
between multiple processes via task files in a directory.
It is not fast and its security relies solely on file permissions and encryption.

!!! Warning
    People who can inject a file in the directory,
    will be able to inject code. Except if you use encryption.

**Store Alias** - `file`

### Parameters

- **directory** - The directory to use. Should be well protected.
- **suffix** - The suffix of task files. Files with other suffixes are ignored.

    <sup>Default: `".task"`</sup>

- **mode** - The mode of the directory.

    <sup>Default: `0o700`</sup>

- **cleanup_directory** - Shall the directory be deleted after shutdown? This will cleanup old tasks.

    <sup>Default: `False`</sup>

- **pickle_protocol**- Pickle protocol level to use (for serialization), defaults to the
highest available.

    <sup>Default: `pickle.HIGHEST_PROTOCOL`</sup>

## RedisStore

**Store Alias** - `redis`

```python
from asyncz.schedulers import AsyncIOScheduler
from asyncz.stores.redis import RedisStore
# assuming redis runs on localhost
scheduler = AsyncIOScheduler(stores={"default": RedisStore()})
# or
scheduler = AsyncIOScheduler(stores={"default": {"type": "redis"}})
```

### Parameters

* **database** - The database number to store tasks in.

    <sup>Default: `0`</sup>

* **tasks_key** - The key to store tasks in.

    <sup>Default: `asyncz.tasks`</sup>

* **run_times_key** - The key to store the tasks run times in.

    <sup>Default: `asyncz.run_times`</sup>

* **pickle_protocol** - Pickle protocol level to use (for serialization), defaults to the
highest available.

    <sup>Default: `pickle.HIGHEST_PROTOCOL`</sup>

* **host** - Host to connect.

    <sup>Default: `localhost`</sup>

* **port** - Port to connect.

    <sup>Default: `6379`</sup>

## MongoDBStore

**Store Alias** - `mongo`

```python
from asyncz.schedulers import AsyncIOScheduler
from asyncz.stores.mongo import MongoDBStore
# assuming mongo db runs on localhost
scheduler = AsyncIOScheduler(stores={"default": MongoDBStore()})
# or
scheduler = AsyncIOScheduler(stores={"default": {"type": "mongo"}})
```



### Parameters

* **database** - The database to store the tasks.

    <sup>Default: `asyncz`</sup>

* **collection** - The collection to store the tasks.

    <sup>Default: `tasks`</sup>

* **client** - A pymongo.mongo_client.MongoClient instance.

    <sup>Default: `None`</sup>

* **pickle_protocol** - Pickle protocol level to use (for serialization), defaults to the highest
available.

    <sup>Default: `pickle.HIGHEST_PROTOCOL`</sup>

* **host** - Host to connect.

    <sup>Default: `localhost`</sup>

* **port** - Port to connect.

    <sup>Default: `27017`</sup>


## SQLAlchemyStore

**Store Alias** - `sqlalchemy`

```python
from asyncz.schedulers import AsyncIOScheduler
from asyncz.stores.sqlalchemy import SQLAlchemyStore

scheduler = AsyncIOScheduler(stores={"default": SQLAlchemyStore(database="sqlite:///./test_suite.sqlite3")})
# or
scheduler = AsyncIOScheduler(stores={"default": {"type": "sqlalchemy", "database": "sqlite:///./test_suite.sqlite3"}})
```

### Parameters

* **database** - The database to store the tasks. Can be string url or engine.

* **tablename** - The tablename.

    <sup>Default: `asyncz_store`</sup>

* **pickle_protocol** - Pickle protocol level to use (for serialization), defaults to the highest
available.

    <sup>Default: `pickle.HIGHEST_PROTOCOL`</sup>

Other kwargs are passed to sqlalchemy.create_engine.


## Custom store

```python
from asyncz.stores.base import BaseStore
```

You might want to use a different store besides the ones provided and that is also possible.
Foor example using a SQLAlchemy or a Tortoise ORM.

To create a custom store **you must** subclass the `BaseStore` and it should implement some
other pieces of functionality as well.

```python
{!> ../../../docs_src/stores/custom.py !}
```
