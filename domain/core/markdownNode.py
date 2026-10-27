"""Markdown 节点及其文件访问、保存实现。"""

from pathlib import Path
from shutil import copyfile

from .data_node import DataNode
from .dataer import Dataer
from .markdown_data import MarkdownData
from .node_info import NodeInfo
from .saver import Saver


class MarkdownDataer(Dataer):
    def __init__(self, data: MarkdownData) -> None:
        self.data = data

    def read(self) -> str:
        with self.data.path.open("r", encoding="utf-8", newline="") as stream:
            return stream.read()

    def write(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("Markdown 内容必须是字符串")
        with self.data.path.open("w", encoding="utf-8", newline="") as stream:
            stream.write(value)


    def query(self, query: str = "") -> str:
        """返回全文，或原样返回包含查询文本的行。"""
        if not isinstance(query, str):
            raise TypeError("查询文本必须是字符串")
        content = self.read()
        if not query:
            return content
        return "".join(line for line in content.splitlines(keepends=True) if query in line)

    def modify(self, old_text: str, new_text: str) -> int:
        """只替换唯一匹配的文本片段，返回替换次数。"""
        if not isinstance(old_text, str) or not isinstance(new_text, str):
            raise TypeError("旧文本和新文本必须是字符串")
        if not old_text:
            raise ValueError("旧文本不能为空")
        content = self.read()
        start = content.find(old_text)
        if start < 0:
            raise ValueError("未找到旧文本")
        if content.find(old_text, start + 1) >= 0:
            raise ValueError("旧文本匹配多处，请提供更多上下文")
        self.write(content[:start] + new_text + content[start + len(old_text):])
        return 1

    def append(self, content: str) -> int:
        """直接追加文件，不读取全文、不补换行，返回追加字符数。"""
        if not isinstance(content, str):
            raise TypeError("追加内容必须是字符串")
        with self.data.path.open("a", encoding="utf-8", newline="") as stream:
            return stream.write(content)


class MarkdownSaver(Saver):
    kind = "markdown"

    def __init__(self, data: MarkdownData) -> None:
        self.data = data

    @property
    def path(self) -> Path:
        return self.data.path

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        copyfile(self.path, destination)


class MarkdownNode(DataNode):
    node_type = "markdown"

    def __init__(self, info: NodeInfo, path: str | Path, *, save_data: bool = True) -> None:
        data = MarkdownData(Path(path))
        super().__init__(
            info,
            dataer=MarkdownDataer(data),
            saver=MarkdownSaver(data),
            save_data=save_data,
        )
