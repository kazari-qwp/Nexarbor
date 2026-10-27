"""原文件原子替换实现，保留 flush/fsync 与失败清理。"""
import os
import tempfile
from pathlib import Path

def atomic_bytes(path, data):
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '.')
    try:
        with os.fdopen(descriptor, 'wb') as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
