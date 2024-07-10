# Stores

In simple terms, the stores are places where, as the name suggests, stores the scheduled tasks.
Asyncz has a `default` store wich is a [MemoryStore](#memoryStore) but also brings an integration
with two major ones, [Redis](#redisstore) and [MongoDB](#mongostore).

Besides the default memory store, the tasks are not store in memory but in the corresponding desired
store.

You are also capable of building your own store if you which, for instance to integrate SQLAlchemy
or Tortoise ORM or anything else. Check out the [custom store](#custom-store) section for more
information.

All the states are serialized and reversed using pydantic objects, so keep that in mind when
creating a [custom store](#custom-store).

## MemoryStore

This is the default store when using Asyncz and probably the one you will be using when running
stateless tasks or tasks that do not require some sort of cache.

**Store Alias** - `memory`

```python
from asyncz.stores.memory import MemoryStore
```

## RedisStore

**Store Alias** - `redis`

```python
from asyncz.stores.redis import RedisStore
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

## MongoDBStore

**Store Alias** - `mongo`

```python
from asyncz.stores.mongo import MongoDBStore
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

## Custom store

```python
from asyncz.stores.base import BaseStore
```

You might want to use a different store besides the ones provided and that is also possible.
Foor example using a SQLAlchemy or a Tortoise ORM.

To create a custom store **you must** subclass the `BaseStore` and it should implement some
other pieces of functionality as well.

```python
{!> ../docs_src/stores/custom.py !}
```
