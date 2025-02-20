nil = b'\x00'


class Cache:
    active = True

    def __init__(self):
        self.cache = {}

    def clear(self, path=None):
        if path is None:
            return self.cache.clear()
        self.cache.pop(path, None)

    def get(self, key):
        if not self.active:
            return nil
        return self.cache.get(key, nil)

    def set(self, key, value):
        self.cache[key] = value


cache = Cache()
