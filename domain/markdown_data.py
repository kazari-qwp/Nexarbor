"""Markdown 数据源：一个真实的磁盘文件。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class MarkdownData:
    path: Path

    def __post_init__(self) -> None:
        self.path = Path(self.path).resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"Markdown 文件不存在：{self.path}")
