"""CSV 节点：主键读写与等值条件查询。"""

from pathlib import Path
import os
import tempfile
from typing import Any

import pandas as pd
from pandas.api.types import is_scalar

from datanet.nodes.node import Node, NodeResult
from datanet.nodes.write_support import validate_write, validate_record


class CsvNode(Node):
    def write(self, key: str, value: Any, *, mode: str = "upsert") -> NodeResult:
        validate_write(key, mode)
        records = self._read_records()
        if isinstance(records, NodeResult):
            return records
        record = validate_record(key, value, self.key_column, records.columns)
        matched = records[self.key_column].eq(key).fillna(False)
        count = int(matched.sum())
        if count > 1:
            return NodeResult(status="error", errors=[f"主键重复：{key}"])
        if count and mode == "insert":
            return NodeResult(status="conflict", errors=[f"主键已存在：{key}"])
        if not count and mode == "update":
            return NodeResult(status="not_found")
        # 在副本上修改，重新应用 dtype；验证失败不触碰原文件。
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
            result = self._result(updated[updated[self.key_column].eq(key)],
                                  {"key": key, "operation": "write", "mode": mode})
            with tempfile.NamedTemporaryFile(dir=self.file_path.parent, delete=False,
                                             suffix=".csv") as file:
                temporary = Path(file.name)
            updated.to_csv(temporary, index=False, encoding="utf-8-sig")
            os.replace(temporary, self.file_path)
            return result
        except (OSError, ValueError, TypeError) as error:
            return NodeResult(status="error", errors=[str(error)])
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def __init__(self, node_id: str, name: str, data_kind: str,
                 file_path: str | Path, key_column: str,
                 dtype: dict[str, Any] | None = None, *, description: str = ""):
        super().__init__(node_id, name, data_kind, description=description)
        self.file_path = Path(file_path).resolve()
        self.key_column = key_column
        self.dtype = dict(dtype or {})
        self.dtype[key_column] = "string"

    def get_schema(self) -> dict:
        columns = list(pd.read_csv(self.file_path, nrows=0, encoding="utf-8-sig").columns)
        if self.key_column not in columns:
            raise ValueError(f"CSV 缺少主键列：{self.key_column}")
        return {"kind": "record", "key_column": self.key_column, "fields": {
            column: {"type": str(self.dtype[column]) if column in self.dtype else None,
                     "type_source": "configured_dtype" if column in self.dtype else "unspecified"}
            for column in columns}}

    def _read_records(self) -> pd.DataFrame | NodeResult:
        try:
            records = pd.read_csv(
                self.file_path, dtype=self.dtype, encoding="utf-8-sig",
                keep_default_na=False, na_values=[""],
            )
        except (OSError, ValueError, pd.errors.ParserError) as error:
            return NodeResult(status="error", errors=[str(error)])
        if self.key_column not in records.columns:
            return NodeResult(status="error", errors=[f"CSV 缺少主键列：{self.key_column}"])
        return records

    def _result(self, records: pd.DataFrame, selection: dict[str, Any]) -> NodeResult:
        records = records.astype(object).where(records.notna(), None)
        return NodeResult(
            items=records.to_dict(orient="records"),
            sources=[{
                "node_id": self.node_id,
                "file": self.file_path.as_posix(),
                "key_column": self.key_column,
                "columns": list(records.columns),
                **selection,
            }],
        )

    def get(self, key: str) -> NodeResult:
        if not isinstance(key, str):
            raise TypeError("查询主键必须是字符串")
        records = self._read_records()
        if isinstance(records, NodeResult):
            return records
        matched = records[records[self.key_column].eq(key).fillna(False)]
        if matched.empty:
            return NodeResult(status="not_found")
        if len(matched) > 1:
            return NodeResult(status="error", errors=[f"主键重复：{key}"])
        return self._result(matched, {"key": key})

    def query(self, filters: dict[str, Any]) -> NodeResult:
        """多个条件按且组合；None 表示筛选该列的缺失值。"""
        if not isinstance(filters, dict):
            raise TypeError("查询条件必须是字典")
        for column, value in filters.items():
            if not isinstance(column, str) or not is_scalar(value):
                raise TypeError("条件列名必须是字符串，值必须是单个标量")
        records = self._read_records()
        if isinstance(records, NodeResult):
            return records
        for column, value in filters.items():
            if column not in records.columns:
                return NodeResult(status="error", errors=[f"CSV 缺少查询列：{column}"])
            mask = records[column].isna() if value is None else records[column].eq(value)
            records = records[mask.fillna(False)]
        # 有来源的空查询结果代表确实查过文件，不是缺少数据节点。
        return self._result(records, {"filters": dict(filters)})
