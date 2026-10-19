"""SQLite 表节点：参数化主键读写，不依赖具体业务配置。"""
import sqlite3
from pathlib import Path
from datanet.core.node import Node, NodeResult
from datanet.core.write_support import validate_write, validate_record

def quote_identifier(name: str) -> str:
    """表名、列名单独引用，支持中文及双引号。"""
    if not isinstance(name, str):
        raise TypeError('表名和列名必须是字符串')
    if not name or '\x00' in name:
        raise ValueError('表名和列名不能为空或包含空字符')
    return '"' + name.replace('"', '""') + '"'

class SqliteNode(Node):
    signal_type = 'sqlite'

    def install_local_tools(self):
        """当前协议由节点上的 data.local 模块显式提供工具。"""
        pass

    def write_many(self, values):
        """Parameterised batch upserts in one database transaction."""
        connection = sqlite3.connect(self.db_path)
        try:
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info({self._table_sql})')]
            rows = [validate_record(str(value[self.key_column]), value, self.key_column, columns) for value in values]
            names = ','.join(quote_identifier(c) for c in columns)
            updates = ','.join(quote_identifier(c)+'=excluded.'+quote_identifier(c) for c in columns if c != self.key_column)
            sql = f'INSERT INTO {self._table_sql} ({names}) VALUES ('+','.join('?' for _ in columns)+f') ON CONFLICT({self._key_sql}) DO UPDATE SET '+updates
            with connection:
                connection.executemany(sql, [[row.get(c) for c in columns] for row in rows])
            return NodeResult(items=[{'written':len(rows)}])
        except (sqlite3.Error, ValueError, TypeError) as error:
            return NodeResult(status='error', errors=[str(error)])
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
                return NodeResult(status='ok' if rows else 'not_found', items=[dict(row) for row in rows], sources=[{'node_id': self.node_id, 'database': str(self.db_path), 'table': self.table_name}])
            finally:
                connection.close()
        except (sqlite3.Error, ValueError) as error:
            return NodeResult(status='error', errors=[str(error)])

    def write(self, key: str, value, *, mode: str='upsert') -> NodeResult:
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
                        return NodeResult(status='error', errors=['表不存在或缺少主键列'])
                    record = validate_record(key, value, self.key_column, names)
                    rows = connection.execute(f'SELECT * FROM {self._table_sql} WHERE {self._key_sql} = ? LIMIT 2', (key,)).fetchall()
                    if len(rows) > 1:
                        return NodeResult(status='error', errors=[f'主键重复：{key}'])
                    if rows and mode == 'insert':
                        return NodeResult(status='conflict', errors=[f'主键已存在：{key}'])
                    if not rows and mode == 'update':
                        return NodeResult(status='not_found')
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
                    result = NodeResult(items=[dict(row)], sources=[{'node_id': self.node_id, 'database': self.db_path.as_posix(), 'table': self.table_name, 'key_column': self.key_column, 'key': key, 'operation': 'write', 'mode': mode}])
                return result
            finally:
                connection.close()
        except sqlite3.Error as error:
            return NodeResult(status='error', errors=[str(error)])

    def __init__(self, node_id: str, name: str, data_kind: str, db_path: str | Path, table_name: str, key_column: str, *, description: str=''):
        super().__init__(node_id, name, data_kind, description=description)
        self.db_path = Path(db_path).resolve()
        self.table_name = table_name
        self.key_column = key_column
        self._table_sql = quote_identifier(table_name)
        self._key_sql = quote_identifier(key_column)

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

    def _read_key(self, key: str) -> NodeResult:
        if not isinstance(key, str):
            raise TypeError('查询主键必须是字符串')
        try:
            connection = sqlite3.connect(Path(str(self.db_path).removeprefix('\\\\?\\')).as_uri() + '?mode=ro', uri=True)
            try:
                connection.row_factory = sqlite3.Row
                columns = connection.execute(f'PRAGMA table_info({self._table_sql})').fetchall()
                if not columns:
                    return NodeResult(status='error', errors=[f'表不存在：{self.table_name}'])
                if self.key_column not in {column['name'] for column in columns}:
                    return NodeResult(status='error', errors=[f'表缺少主键列：{self.key_column}'])
                rows = connection.execute(f'SELECT * FROM {self._table_sql} WHERE {self._key_sql} = ? LIMIT 2', (key,)).fetchall()
            finally:
                connection.close()
        except sqlite3.Error as error:
            return NodeResult(status='error', errors=[str(error)])
        if not rows:
            return NodeResult(status='not_found')
        if len(rows) > 1:
            return NodeResult(status='error', errors=[f'主键重复：{key}'])
        return NodeResult(items=[dict(rows[0])], sources=[{'node_id': self.node_id, 'database': self.db_path.as_posix(), 'table': self.table_name, 'key_column': self.key_column, 'key': key}])
