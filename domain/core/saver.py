"""数据节点的文件保存接口。"""

from abc import ABC, abstractmethod
from pathlib import Path


class Saver(ABC):
    kind: str

    @property
    @abstractmethod
    def path(self) -> Path:
        """当前数据源的文件路径。"""
        pass

    @abstractmethod
    def save(self, path: str | Path) -> None:
        """把数据保存到指定的新位置，不改变当前数据源。"""
        pass
