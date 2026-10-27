"""原 CSV 数据规则移入 Dataer；节点只负责组合新 DataNode。"""

from pathlib import Path
import os
import tempfile
from typing import Any
import pandas as pd
from pandas.api.types import is_scalar
from domain.core import DataNode, NodeInfo
from domain.data_result import DataResult
from domain.data_write import validate_write, validate_record
from domain.record_dataer import RecordDataer
from .files import FileData, FileSaver

class CsvDataer(RecordDataer):
    def __init__(self, data: FileData, node_id: str, key_column: str, dtype: dict | None = None):
        self.data, self.node_id = data, node_id
        self.key_column = key_column
        self.dtype = dict(dtype or {})
        self.dtype[key_column] = "string"

    @property
    def file_path(self) -> Path:
        return self.data.path


    def write_many(self, values):
        """Upsert a batch with one file replacement; caller owns collection write locking."""
        records = self._read_records()
        if isinstance(records, DataResult):
            return records
        rows = [validate_record(str(value[self.key_column]), value, self.key_column, records.columns) for value in values]
        keys = [row[self.key_column] for row in rows]
        if len(keys) != len(set(keys)):
            return DataResult(status='error', errors=['Batch contains duplicate primary keys'])
        updated = pd.concat([records[~records[self.key_column].isin(keys)], pd.DataFrame(rows)], ignore_index=True).astype(self.dtype)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=self.file_path.parent, delete=False, suffix='.csv') as file:
            temporary = Path(file.name)
        try:
            updated.to_csv(temporary, index=False, encoding='utf-8-sig')
            os.replace(temporary, self.file_path)
            return DataResult(items=[{'written': len(rows)}])
        finally:
            temporary.unlink(missing_ok=True)

    def write(self, key: str, value: Any, *, mode: str='upsert') -> DataResult:
        validate_write(key, mode)
        records = self._read_records()
        if isinstance(records, DataResult):
            return records
        record = validate_record(key, value, self.key_column, records.columns)
        matched = records[self.key_column].eq(key).fillna(False)
        count = int(matched.sum())
        if count > 1:
            return DataResult(status='error', errors=[f'主键重复：{key}'])
        if count and mode == 'insert':
            return DataResult(status='conflict', errors=[f'主键已存在：{key}'])
        if not count and mode == 'update':
            return DataResult(status='not_found')
        updated = records.astype(object).copy()
        if count:
            index = updated.index[matched][0]
            for column, item in record.items():
                updated.at[index, column] = item
        else:
            updated = pd.concat([updated, pd.DataFrame([record])], ignore_index=True)
        temporary = None
        try:
            updated = updated.astype(self.dtype)
            result = self._result(updated[updated[self.key_column].eq(key)], {'key': key, 'operation': 'write', 'mode': mode})
            with tempfile.NamedTemporaryFile(dir=self.file_path.parent, delete=False, suffix='.csv') as file:
                temporary = Path(file.name)
            updated.to_csv(temporary, index=False, encoding='utf-8-sig')
            os.replace(temporary, self.file_path)
            return result
        except (OSError, ValueError, TypeError) as error:
            return DataResult(status='error', errors=[str(error)])
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def get_schema(self) -> dict:
        columns = list(pd.read_csv(self.file_path, nrows=0, encoding='utf-8-sig').columns)
        if self.key_column not in columns:
            raise ValueError(f'CSV 缺少主键列：{self.key_column}')
        return {'kind': 'record', 'key_column': self.key_column, 'fields': {column: {'type': str(self.dtype[column]) if column in self.dtype else None, 'type_source': 'configured_dtype' if column in self.dtype else 'unspecified'} for column in columns}}

    def _read_records(self) -> pd.DataFrame | DataResult:
        try:
            records = pd.read_csv(self.file_path, dtype=self.dtype, encoding='utf-8-sig', keep_default_na=False, na_values=[''])
        except (OSError, ValueError, pd.errors.ParserError) as error:
            return DataResult(status='error', errors=[str(error)])
        if self.key_column not in records.columns:
            return DataResult(status='error', errors=[f'CSV 缺少主键列：{self.key_column}'])
        return records

    def _result(self, records: pd.DataFrame, selection: dict[str, Any]) -> DataResult:
        records = records.astype(object).where(records.notna(), None)
        return DataResult(items=records.to_dict(orient='records'), sources=[{'node_id': self.node_id, 'file': self.file_path.as_posix(), 'key_column': self.key_column, 'columns': list(records.columns), **selection}])

    def _read_key(self, key: str) -> DataResult:
        if not isinstance(key, str):
            raise TypeError('查询主键必须是字符串')
        records = self._read_records()
        if isinstance(records, DataResult):
            return records
        matched = records[records[self.key_column].eq(key).fillna(False)]
        if matched.empty:
            return DataResult(status='not_found')
        if len(matched) > 1:
            return DataResult(status='error', errors=[f'主键重复：{key}'])
        return self._result(matched, {'key': key})

    def _read_filter(self, filters: dict[str, Any]) -> DataResult:
        """多个条件按且组合；None 表示筛选该列的缺失值。"""
        if not isinstance(filters, dict):
            raise TypeError('查询条件必须是字典')
        for column, value in filters.items():
            if not isinstance(column, str) or not is_scalar(value):
                raise TypeError('条件列名必须是字符串，值必须是单个标量')
        records = self._read_records()
        if isinstance(records, DataResult):
            return records
        for column, value in filters.items():
            if column not in records.columns:
                return DataResult(status='error', errors=[f'CSV 缺少查询列：{column}'])
            mask = records[column].isna() if value is None else records[column].eq(value)
            records = records[mask.fillna(False)]
        return self._result(records, {'filters': dict(filters)})

class CsvSaver(FileSaver):
    kind = "csv"


class CsvNode(DataNode):
    node_type = 'csv'
    def __init__(self, info: NodeInfo, path: str | Path, key_column: str, dtype: dict | None = None, *, save_data: bool = True):
        data = FileData(Path(path))
        super().__init__(info, dataer=CsvDataer(data, info.node_id, key_column, dtype), saver=CsvSaver(data), save_data=save_data)

    @property
    def parameters(self) -> dict:
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in self.dataer.dtype.items()):
            raise ValueError("保存 CSV dtype 时请使用字符串类型名，例如 Int64")
        return {"key_column": self.dataer.key_column, "dtype": dict(self.dataer.dtype)}
