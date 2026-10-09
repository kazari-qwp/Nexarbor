"""只读 CSV 节点：主键读取与等值条件查询。"""

from pathlib import Path
from typing import Any

import pandas as pd
from pandas.api.types import is_scalar

from datanet.nodes.node import Node, NodeResult


class CsvNode(Node):
    def __init__(self, node_id: str, name: str, data_kind: str,
                 file_path: str | Path, key_column: str,
                 dtype: dict[str, Any] | None = None):
        super().__init__(node_id, name, data_kind)
        self.file_path = Path(file_path).resolve()
        self.key_column = key_column
        self.dtype = dict(dtype or {})
        self.dtype[key_column] = "string"

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
