from collections.abc import MutableMapping

class CaseInsensitiveDict(MutableMapping):
    def __init__(self, *args, **kwargs):
        self.store = {k.lower(): v for k, v in dict(*args, **kwargs).items()}

    def __getitem__(self, key):
        return self.store[key.lower()]

    def __setitem__(self, key, value):
        self.store[key.lower()] = value

    def __delitem__(self, key):
        del self.store[key.lower()]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)