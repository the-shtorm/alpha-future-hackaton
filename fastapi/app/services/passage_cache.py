import hashlib
import json
from collections import OrderedDict


class PassageCache:
    """Owned by the single inference thread; stores no product metadata."""

    def __init__(self, capacity=512):
        self.capacity = capacity
        self.values = OrderedDict()
        self.hits = self.misses = 0

    @staticmethod
    def key(text, model_id, revision, template="passage-v2", labels="ru-v2"):
        return hashlib.sha256(
            json.dumps([text, model_id, revision, template, labels], ensure_ascii=False).encode()
        ).hexdigest()

    def get(self, key):
        if key not in self.values:
            self.misses += 1
            return None
        self.hits += 1
        self.values.move_to_end(key)
        return self.values[key]

    def put(self, key, vector):
        self.values[key] = vector
        self.values.move_to_end(key)
        while len(self.values) > self.capacity:
            self.values.popitem(last=False)
