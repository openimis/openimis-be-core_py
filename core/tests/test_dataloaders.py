from django.test import SimpleTestCase

from core.dataloaders import DataLoader


class _RecordingLoader(DataLoader):
    def __init__(self):
        super().__init__()
        self.batches = []

    def batch_load_fn(self, keys):
        self.batches.append(list(keys))
        return [f"value-{key}" if key != "missing" else None for key in keys]


class DataLoaderTest(SimpleTestCase):
    def test_load_returns_the_value_itself(self):
        # graphql-core 3 does not resolve promise.Promise objects returned by a
        # resolver: the value must come back directly.
        self.assertEqual(_RecordingLoader().load(1), "value-1")

    def test_load_caches_per_loader(self):
        loader = _RecordingLoader()
        loader.load(1)
        loader.load(1)
        self.assertEqual(loader.batches, [[1]])

    def test_load_many_fetches_uncached_keys_in_one_batch(self):
        loader = _RecordingLoader()
        loader.load(2)
        self.assertEqual(loader.load_many([1, 2, 3]), ["value-1", "value-2", "value-3"])
        self.assertEqual(loader.batches, [[2], [1, 3]])

    def test_missing_key_gives_none(self):
        self.assertIsNone(_RecordingLoader().load("missing"))

    def test_accepts_a_promise_from_batch_load_fn(self):
        from promise import Promise

        class PromiseLoader(DataLoader):
            def batch_load_fn(self, keys):
                return Promise.resolve([key * 10 for key in keys])

        self.assertEqual(PromiseLoader().load_many([1, 2]), [10, 20])
