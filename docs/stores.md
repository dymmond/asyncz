# Stores

In simple terms, the stores are places where, as the name suggests, stores the scheduled jobs.
Asyncz has a `default` store wich is a [MemoryStore](#memoryStore) but also brings an integration
with two major ones, [Redis](#redisstore) and [MongoDB](#mongostore).

Besides the default memory store, the jobs are not store in memory but in the corresponding desired
store.

You are also capable of building your own store if you which, for instance to integrate SQLAlchemy
or Tortoise ORM or anything else. Check out the [custom store](#custom-store) section for more
information.

## MemoryStore

## RedisStore

## MongoDBStore

## Custom store
