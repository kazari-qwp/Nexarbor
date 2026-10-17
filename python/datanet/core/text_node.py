"""One UTF-8 text/Markdown file per node; writes keep its previous bytes."""
import os
import tempfile
from pathlib import Path
from threading import RLock
from datanet.core.node import Node, NodeResult
from datanet.core.write_support import validate_write

class TextFileNode(Node):
    signal_type = 'text_file'

    def __init__(self, node_id, name, data_kind, file_path, *, description='', max_chars=None, tool_channels=None):
        super().__init__(node_id, name, data_kind, description=description)
        if max_chars is not None and (type(max_chars) is not int or max_chars < 1):
            raise ValueError('max_chars 必须为正整数')
        from .json_values import names
        if tool_channels is not None and (not isinstance(tool_channels,dict) or set(tool_channels)-{'read','write','get_schema'}):raise ValueError('Invalid text tool channel configuration')
        self.tool_channels={name:list(names((tool_channels or {}).get(name,()),'tool_channels')) for name in ('read','write','get_schema')}
        self.max_chars = max_chars
        self.file_path = Path(file_path).resolve()
        self._lock = RLock()
        self.register_tool('read', self.read, description='读取本节点绑定的UTF-8文件，主键为content', parameters={'type': 'object', 'properties': {'request': {'type': 'object', 'properties': {'method': {'const': 'key'}, 'key': {'const': 'content'}}, 'required': ['method', 'key'], 'additionalProperties': False}}, 'required': ['request'], 'additionalProperties': False}, access_channels=self.tool_channels['read'])
        self.register_tool('write', self.write, description='创建、替换或追加本节点文本；主键content；写前保留上一版.bak；append原样追加不补换行', parameters={'type': 'object', 'properties': {'key': {'const': 'content'}, 'value': {'type': 'string'}, 'mode': {'enum': ['insert', 'update', 'upsert', 'append']}}, 'required': ['key', 'value'], 'additionalProperties': False}, access_channels=self.tool_channels['write'])
    @property
    def backup_path(self):
        return self.file_path.with_name(self.file_path.name + '.bak')

    def get_schema(self):
        return {'kind': 'text_file', 'key': 'content', 'encoding': 'utf-8', 'file_path': str(self.file_path), 'backup_path': str(self.backup_path)}

    def _read_key(self, key):
        if key != 'content':
            return NodeResult(status='not_found')
        with self._lock:
            try:
                content = self.file_path.read_text(encoding='utf-8')
            except FileNotFoundError:
                return NodeResult(status='not_found')
            except (OSError, UnicodeError) as error:
                return NodeResult(status='error', errors=[str(error)])
            return NodeResult(items=[{'content': content}], sources=[{'node_id': self.node_id, 'file_path': str(self.file_path), 'key': 'content'}])

    @staticmethod
    def _atomic_bytes(path, data):
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '.')
        try:
            with os.fdopen(descriptor, 'wb') as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def _commit(self, text, operation):
        if self.max_chars is not None and len(text) > self.max_chars:
            return NodeResult(status='error', errors=[f'正文共{len(text)}字符，最多{self.max_chars}字符；请精简后重试。'])
        try:
            data = text.encode('utf-8')
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            if self.file_path.exists():
                self._atomic_bytes(self.backup_path, self.file_path.read_bytes())
            self._atomic_bytes(self.file_path, data)
            result = self._read_key('content')
            result.sources[0].update(operation=operation, backup_path=str(self.backup_path) if self.backup_path.exists() else None)
            result.items = [{'node_id': self.node_id, 'written': True}]
            return result
        except (OSError, UnicodeError) as error:
            return NodeResult(status='error', errors=[str(error)])

    def write(self, key, value, *, mode='upsert'):
        validate_write(key, mode, allow_append=True)
        if key != 'content':
            return NodeResult(status='not_found')
        if not isinstance(value, str):
            raise TypeError('文本内容必须是字符串')
        with self._lock:
            exists = self.file_path.exists()
            if mode == 'insert' and exists:
                return NodeResult(status='conflict')
            if mode == 'update' and (not exists):
                return NodeResult(status='not_found')
            if mode == 'append':
                result = self._read_key('content')
                if result.status not in ('ok', 'not_found'):
                    return result
                current = result.items[0]['content'] if result.status == 'ok' else ''
                return self._commit(current + value, 'append')
            return self._commit(value, 'write')
