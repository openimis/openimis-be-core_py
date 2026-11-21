class DataLoader:
    """Per-request loader with a cache, for graphene 3's synchronous execution.

    Subclasses implement ``batch_load_fn(keys)`` and return the values in the
    order of ``keys`` (``None`` for a missing one), as with ``promise.dataloader``.

    graphql-core 3 does not resolve the ``promise.Promise`` objects that
    ``promise.dataloader.DataLoader.load`` returns, so ``load`` here returns the
    value itself. A fresh instance is made per request (``get_dataloaders``),
    which bounds the cache to one request. ``load_many`` fetches every key not
    cached yet in a single batch.
    """

    def __init__(self):
        self._cache = {}

    def batch_load_fn(self, keys):
        raise NotImplementedError

    def load(self, key):
        return self.load_many([key])[0]

    def load_many(self, keys):
        missing = list(dict.fromkeys(key for key in keys if key not in self._cache))
        if missing:
            values = self.batch_load_fn(missing)
            if hasattr(values, "get") and not isinstance(values, (dict, list, tuple)):
                # A promise.Promise from a loader written for promise.dataloader.
                values = values.get()
            self._cache.update(zip(missing, values))
        return [self._cache[key] for key in keys]

    def clear(self, key):
        self._cache.pop(key, None)
        return self

    def clear_all(self):
        self._cache.clear()
        return self

    def prime(self, key, value):
        self._cache.setdefault(key, value)
        return self
