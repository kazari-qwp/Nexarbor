"""原 SQLITE 数据规则移入 Dataer；节点只负责组合新 DataNode。"""

import sqlite3
from pathlib import Path
from domain.core import DataNode, NodeInfo
from domain.data_result import DataResult
from domain.data_write import validate_write, validate_record
from domain.record_dataer import RecordDataer
from .files import FileData, FileSaver

def quote_identifier(name: str) -> str:
    """表名、列名单独引用，支持中文及双引号。"""
    if not isinstance(name, str):
        raise TypeError('表名和列名必须是字符串')
    if not name or '\x00' in name:
        raise ValueError('表名和列名不能为空或包含空字符')
    return '"' + name.replace('"', '""') + '"'

class SqliteDataer(RecordDataer):
    def __init__(self, data: FileData, node_id: str, table_name: str, key_column: str):
        self.data, self.node_id = data, node_id
        self.table_name, self.key_column = table_name, key_column
        self._table_sql, self._key_sql = quote_identifier(table_name), quote_identifier(key_column)

    @property
    def db_path(self) -> Path:
        return self.data.path


    def write_many(self, values):
        """Parameterised batch upserts in one database transaction."""
        connection = sqlite3.connect(self.db_path)
        try:
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info({self._table_sql})')]
            rows = [validate_record(str(value[self.key_column]), value, self.key_column, columns) for value in values]
            names = ','.join((quote_identifier(c) for c in columns))
            updates = ','.join((quote_identifier(c) + '=excluded.' + quote_identifier(c) for c in columns if c != self.key_column))
            sql = f'INSERT INTO {self._table_sql} ({names}) VALUES (' + ','.join(('?' for _ in columns)) + f') ON CONFLICT({self._key_sql}) DO UPDATE SET ' + updates
            with connection:
                connection.executemany(sql, [[row.get(c) for c in columns] for row in rows])
            return DataResult(items=[{'written': len(rows)}])
        except (sqlite3.Error, ValueError, TypeError) as error:
            return DataResult(status='error', errors=[str(error)])
        finally:
            connection.close()

    def _read_filter(self, filters):
        try:
            connection = sqlite3.connect(Path(str(self.db_path).removeprefix('\\\\?\\')).as_uri() + '?mode=ro', uri=True)
            try:
                connection.row_factory = sqlite3.Row
                names = {row['name'] for row in connection.execute(f'PRAGMA table_info({self._table_sql})')}
                clauses, values = ([], [])
                for key, value in filters.items():
                    if key.startswith('metadata.') and 'metadata' in names:
                        field = key[len('metadata.'):]
                        if not field or not all((c.isalnum() or c == '_' for c in field)):
                            raise ValueError('元数据字段仅支持字母、数字和下划线')
                        path = '$."' + field + '"'
                        expression = 'json_extract(' + quote_identifier('metadata') + ", '" + path + "')"
                    elif key in names:
                        expression = quote_identifier(key)
                    else:
                        raise ValueError(f'未知列：{key}')
                    if value is not None and type(value) not in (str, int, float, bool):
                        raise ValueError('条件值必须为 SQLite 标量')
                    clauses.append(expression + (' IS NULL' if value is None else ' = ?'))
                    if value is not None:
                        values.append(value)
                where = ' AND '.join(clauses) or '1'
                rows = connection.execute(f'SELECT * FROM {self._table_sql} WHERE {where} ORDER BY {self._key_sql}', values).fetchall()
                return DataResult(status='ok' if rows else 'not_found', items=[dict(row) for row in rows], sources=[{'node_id': self.node_id, 'database': str(self.db_path), 'table': self.table_name}])
            finally:
                connection.close()
        except (sqlite3.Error, ValueError) as error:
            return DataResult(status='error', errors=[str(error)])

    def write(self, key: str, value, *, mode: str='upsert') -> DataResult:
        validate_write(key, mode)
        try:
            connection = sqlite3.connect(Path(str(self.db_path).removeprefix('\\\\?\\')).as_uri() + '?mode=rw', uri=True)
            try:
                connection.row_factory = sqlite3.Row
                with connection:
                    connection.execute('BEGIN IMMEDIATE')
                    columns = connection.execute(f'PRAGMA table_info({self._table_sql})').fetchall()
                    names = {column['name'] for column in columns}
                    if self.key_column not in names:
                        return DataResult(status='error', errors=['表不存在或缺少主键列'])
                    record = validate_record(key, value, self.key_column, names)
                    rows = connection.execute(f'SELECT * FROM {self._table_sql} WHERE {self._key_sql} = ? LIMIT 2', (key,)).fetchall()
                    if len(rows) > 1:
                        return DataResult(status='error', errors=[f'主键重复：{key}'])
                    if rows and mode == 'insert':
                        return DataResult(status='conflict', errors=[f'主键已存在：{key}'])
                    if not rows and mode == 'update':
                        return DataResult(status='not_found')
                    if rows:
                        fields = [column for column in record if column != self.key_column]
                        if fields:
                            assignments = ', '.join((f'{quote_identifier(column)} = ?' for column in fields))
                            connection.execute(f'UPDATE {self._table_sql} SET {assignments} WHERE {self._key_sql} = ?', [record[column] for column in fields] + [key])
                    else:
                        fields = list(record)
                        identifiers = ', '.join((quote_identifier(column) for column in fields))
                        placeholders = ', '.join(('?' for _ in fields))
                        connection.execute(f'INSERT INTO {self._table_sql} ({identifiers}) VALUES ({placeholders})', [record[column] for column in fields])
                    row = connection.execute(f'SELECT * FROM {self._table_sql} WHERE {self._key_sql} = ?', (key,)).fetchone()
                    result = DataResult(items=[dict(row)], sources=[{'node_id': self.node_id, 'database': self.db_path.as_posix(), 'table': self.table_name, 'key_column': self.key_column, 'key': key, 'operation': 'write', 'mode': mode}])
                return result
            finally:
                connection.close()
        except sqlite3.Error as error:
            return DataResult(status='error', errors=[str(error)])

    def get_schema(self) -> dict:
        try:
            connection = sqlite3.connect(Path(str(self.db_path).removeprefix('\\\\?\\')).as_uri() + '?mode=ro', uri=True)
            try:
                connection.row_factory = sqlite3.Row
                columns = connection.execute(f'PRAGMA table_info({self._table_sql})').fetchall()
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise ValueError(f'读取 SQLite 结构失败：{error}') from error
        if not columns or self.key_column not in {column['name'] for column in columns}:
            raise ValueError('表不存在或缺少主键列')
        return {'kind': 'record', 'table': self.table_name, 'key_column': self.key_column, 'fields': {column['name']: {'type': column['type'] or None, 'not_null': bool(column['notnull']), 'primary_key_order': column['pk'], 'default': column['dflt_value']} for column in columns}}

    def _read_key(self, key: str) -> DataResult:
        if not isinstance(key, str):
            raise TypeError('查询主键必须是字符串')
        try:
            connection = sqlite3.connect(Path(str(self.db_path).removeprefix('\\\\?\\')).as_uri() + '?mode=ro', uri=True)
            try:
                connection.row_factory = sqlite3.Row
                columns = connection.execute(f'PRAGMA table_info({self._table_sql})').fetchall()
                if not columns:
                    return DataResult(status='error', errors=[f'表不存在：{self.table_name}'])
                if self.key_column not in {column['name'] for column in columns}:
                    return DataResult(status='error', errors=[f'表缺少主键列：{self.key_column}'])
                rows = connection.execute(f'SELECT * FROM {self._table_sql} WHERE {self._key_sql} = ? LIMIT 2', (key,)).fetchall()
            finally:
                connection.close()
        except sqlite3.Error as error:
            return DataResult(status='error', errors=[str(error)])
        if not rows:
            return DataResult(status='not_found')
        if len(rows) > 1:
            return DataResult(status='error', errors=[f'主键重复：{key}'])
        return DataResult(items=[dict(rows[0])], sources=[{'node_id': self.node_id, 'database': self.db_path.as_posix(), 'table': self.table_name, 'key_column': self.key_column, 'key': key}])

class SqliteSaver(FileSaver):
    kind = "sqlite"

    def save(self, path: str | Path) -> None:
        # 原资源快照使用 SQLite backup，必须包含已提交的 WAL 页面。
        from app.persistence.resource_data import read_bytes
        destination = Path(path)
        if destination.resolve() == self.path:
            raise ValueError("保存目标不能是当前数据库文件")
        content = read_bytes(self.path)
        if content is None:
            raise FileNotFoundError(self.path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


class SqliteNode(DataNode):
    def __init__(self, info: NodeInfo, path: str | Path, table_name: str, key_column: str, *, save_data: bool = True):
        data = FileData(Path(path))
        super().__init__(info, dataer=SqliteDataer(data, info.node_id, table_name, key_column), saver=SqliteSaver(data), save_data=save_data)

    @property
    def parameters(self) -> dict:
        return {"table_name": self.dataer.table_name, "key_column": self.dataer.key_column}
