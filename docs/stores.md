# Stores

In simple terms, the stores are places where, as the name suggests, stores the scheduled tasks.
Asyncz has a `default` store wich is a [MemoryStore](#memoryStore) but also brings an integration
with two major ones, [Redis](#redisstore) and [MongoDB](#mongostore).

Besides the default memory store, the tasks are not store in memory but in the corresponding desired
store.

You are also capable of building your own store if you which, for instance to integrate SQLAlchemy
or Tortoise ORM or anything else. Check out the [custom store](#custom-store) section for more
information.

## MemoryStore

This is the default store when using Asyncz and probably the one you will be using when running
stateless tasks or tasks that do not require some sort of cache.

**Store Alias** - `memory`

```python
from asyncz.stores import MemoryStore
```

## RedisStore

## MongoDBStore

## Custom store
