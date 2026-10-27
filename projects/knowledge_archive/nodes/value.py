"""文件单值节点；JSON 路径字符串仍是普通值，不解引用。"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
from shutil import copyfile
from tempfile import NamedTemporaryFile
from typing import Any

from domain.core import DataNode, NodeInfo, Saver
from domain.data_result import DataResult
from domain.data_write import validate_write
from domain.record_dataer import RecordDataer


@dataclass
class ValueData:
    path: Path

    def __post_init__(self):
        self.path = Path(self.path).resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"JSON 值文件不存在：{self.path}")


class ValueDataer(RecordDataer):
    def __init__(self, data: ValueData, node_id: str):
        self.data, self.node_id = data, node_id

    def _read_value(self) -> Any:
        return json.loads(self.data.path.read_text(encoding="utf-8-sig"))

    def _write_value(self, value: Any) -> None:
        content = json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n"
        temporary = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.data.path.parent,
                                    prefix=".value-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.data.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def write(self, key: str, value: Any, *, mode: str = "upsert") -> DataResult:
        validate_write(key, mode)
        if key != "value":
            return DataResult(status="not_found", errors=["单值节点只支持主键 value"])
        if mode == "insert":
            return DataResult(status="conflict", errors=["单值节点的 value 已存在"])
        self._write_value(value)
        result = self._read_key(key)
        result.sources[0].update(operation="write", mode=mode)
        return result

    def get_schema(self) -> dict:
        value = self._read_value()
        names = {type(None): "null", bool: "boolean", int: "integer", float: "number",
                 str: "string", list: "array", dict: "object"}
        return {"kind": "single_value", "key": "value", "value_type": names.get(type(value)),
                "python_type": type(value).__name__}

    def _read_key(self, key: str) -> DataResult:
        if not isinstance(key, str):
            raise TypeError("查询主键必须是字符串")
        if key != "value":
            return DataResult(status="not_found")
        return DataResult(items=[{"value": self._read_value()}], sources=[{
            "node_id": self.node_id, "storage": "file", "file": str(self.data.path), "key": "value",
        }])


class ValueSaver(Saver):
    kind = "value"

    def __init__(self, data: ValueData):
        self.data = data

    @property
    def path(self) -> Path:
        return self.data.path

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        copyfile(self.path, destination)


class ValueNode(DataNode):
    def __init__(self, info: NodeInfo, path: str | Path, *, save_data: bool = True):
        data = ValueData(Path(path))
        super().__init__(info, dataer=ValueDataer(data, info.node_id), saver=ValueSaver(data), save_data=save_data)
