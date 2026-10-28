"""普通文本工具的原子写入和上一版备份；核心 Dataer 保持原行为。"""
from adapt.files.atomic import atomic_bytes
from domain.record_dataer import RecordDataer
from domain.data_result import DataResult
from domain.data_write import validate_write


class TextFileAccess(RecordDataer):
    def __init__(self, node, *, max_chars=None):
        self.file_path = node.saver.path
        self.node_id = node.info.node_id
        self.max_chars = max_chars

    @property
    def backup_path(self):
        return self.file_path.with_name(self.file_path.name + ".bak")

    def get_schema(self):
        return dict(kind="text_file", key="content", encoding="utf-8", file_path=str(self.file_path), backup_path=str(self.backup_path))

    def _read_key(self, key):
        if key != "content":
            return DataResult(status="not_found")
        try:
            content = self.file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return DataResult(status="not_found")
        except (OSError, UnicodeError) as error:
            return DataResult(status="error", errors=[str(error)])
        return DataResult(items=[dict(content=content)], sources=[dict(node_id=self.node_id, file_path=str(self.file_path), key="content")])

    def _commit(self, text, operation):
        if self.max_chars is not None and len(text) > self.max_chars:
            return DataResult(status="error", errors=[f"正文共{len(text)}字符，最多{self.max_chars}字符；请精简后重试。"])
        try:
            data = text.encode("utf-8")
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            if self.file_path.exists():
                atomic_bytes(self.backup_path, self.file_path.read_bytes())
            atomic_bytes(self.file_path, data)
            return DataResult(items=[dict(node_id=self.node_id, written=True)], sources=[dict(node_id=self.node_id, file_path=str(self.file_path), key="content", operation=operation, backup_path=str(self.backup_path) if self.backup_path.exists() else None)])
        except (OSError, UnicodeError) as error:
            return DataResult(status="error", errors=[str(error)])

    def write(self, key, value, *, mode="upsert"):
        validate_write(key, mode, allow_append=True)
        if key != "content":
            return DataResult(status="not_found")
        if not isinstance(value, str):
            raise TypeError("文本内容必须是字符串")
        exists = self.file_path.exists()
        if mode == "insert" and exists:
            return DataResult(status="conflict")
        if mode == "update" and not exists:
            return DataResult(status="not_found")
        if mode == "append":
            result = self._read_key("content")
            if result.status not in ("ok", "not_found"):
                return result
            current = result.items[0]["content"] if result.status == "ok" else ""
            return self._commit(current + value, "append")
        return self._commit(value, "write")
