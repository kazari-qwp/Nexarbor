"""Keep Windows extended paths intact at the fsspec boundary."""
import os
from pathlib import Path
from fsspec.implementations.local import LocalFileSystem
from datanet.core.storage_paths import storage_path


class WindowsLocalFileSystem(LocalFileSystem):
    @classmethod
    def _strip_protocol(cls,path):
        # fsspec converts \\?\ paths to //?/ paths, which Win32 rejects.
        return str(storage_path(super()._strip_protocol(path).replace('/', chr(92))))

    @classmethod
    def _parent(cls,path):
        return str(Path(cls._strip_protocol(path)).parent)


def local_filesystem():
    return WindowsLocalFileSystem() if os.name=='nt' else LocalFileSystem()
