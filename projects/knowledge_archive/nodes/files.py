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
