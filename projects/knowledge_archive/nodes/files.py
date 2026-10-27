"""文件数据及普通文件保存；不创建或替换调用者的数据源。"""

from dataclasses import dataclass
from pathlib import Path
from shutil import copyfile

from domain.core import Saver


@dataclass
class FileData:
    path: Path

    def __post_init__(self):
        self.path = Path(self.path).resolve()


class FileSaver(Saver):
    def __init__(self, data: FileData):
        self.data = data

    @property
    def path(self) -> Path:
        return self.data.path

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        copyfile(self.path, destination)


@dataclass
class DirectoryData(FileData):
    def __post_init__(self):
        super().__post_init__()
        self.path.mkdir(parents=True, exist_ok=True)


class DirectorySaver(FileSaver):
    def __init__(self, data: DirectoryData, lock):
        super().__init__(data)
        self.lock = lock

    def save(self, path: str | Path) -> None:
        from app.persistence.resource_data import read_bytes
        destination = Path(path).resolve()
        if destination.is_relative_to(self.path):
            raise ValueError("目录副本不能位于源目录内部")
        with self.lock:
            destination.mkdir(parents=True, exist_ok=True)
            for source in sorted(self.path.rglob("*")):
                # 沿用原 resource_paths：运行锁、SQLite 伴随文件和临时文件不随节点保存。
                if source.is_symlink():
                    raise ValueError("Linked node resources are not portable")
                target = destination / source.relative_to(self.path)
                if source.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                elif source.is_file() and not source.name.endswith((".lock", "-wal", "-shm", "-journal", ".tmp")):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(read_bytes(source))
