"""Versioned local storage. Readers/writers share an OS-level file lock."""
import json
import os
from pathlib import Path
from uuid import uuid4
from filelock import FileLock
from .local_fs import local_filesystem

class VersionStorage:

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.lock = FileLock(str(self.path) + '.lock', timeout=60)

    def version(self):
        pointer = self.path / 'current.json'
        if not pointer.exists():
            return None
        version = json.loads(pointer.read_text(encoding='utf-8'))['version']
        if not isinstance(version, str) or len(version) != 32 or any((c not in '0123456789abcdef' for c in version)):
            raise ValueError('非法索引版本')
        return version

    def folder(self, version):
        return self.path / 'versions' / version

    def commit(self, index, settings, validate):
        version = uuid4().hex
        folder = self.folder(version)
        folder.mkdir(parents=True)
        index.storage_context.persist(persist_dir=str(folder),fs=local_filesystem())
        (folder / 'node_config.json').write_text(json.dumps(settings), encoding='utf-8')
        restored = validate(folder)
        for path in folder.iterdir():
            if path.is_file():
                with path.open('r+b') as file:
                    os.fsync(file.fileno())
        temporary = self.path / (version + '.tmp')
        try:
            with temporary.open('w', encoding='utf-8') as file:
                json.dump({'version': version}, file)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path / 'current.json')
        finally:
            temporary.unlink(missing_ok=True)
        return (version, restored)
