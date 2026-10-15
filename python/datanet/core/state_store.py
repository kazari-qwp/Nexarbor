"""Atomic JSON persistence for component state, with process-local serialization."""
from copy import deepcopy
from pathlib import Path
from threading import RLock
from uuid import uuid4
import json


class JsonStore:
    def __init__(self, file, defaults):
        self.file, self.lock = Path(file), RLock()
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.data = json.loads(self.file.read_text(encoding='utf-8')) if self.file.exists() else deepcopy(defaults)
        self.save()

    def save(self):
        with self.lock:
            temporary = self.file.with_name(self.file.name + '.' + uuid4().hex + '.tmp')
            temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
            temporary.replace(self.file)

    def mutate(self, fn):
        with self.lock:
            before = deepcopy(self.data)
            try:
                result = fn(self.data)
                self.save()
                return deepcopy(result)
            except Exception:
                self.data = before
                raise
