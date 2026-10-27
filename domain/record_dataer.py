"""结构化节点的查询分派；具体存储行为由 Dataer 子类实现。"""

from .core import Dataer
from .data_request import validate_request
from .data_result import DataResult


class RecordDataer(Dataer):
    def read(self, request: dict) -> DataResult:
        request = validate_request(request)
        method = request["method"]
        if method == "key":
            return self._read_key(request["key"])
        if method == "filter":
            return self._read_filter(request["filters"])
        return self._read_semantic(request["query"], request.get("top_k", 5))

    def _read_key(self, key: str) -> DataResult:
        return DataResult(status="unsupported", errors=["节点不支持主键读取"])

    def _read_filter(self, filters: dict) -> DataResult:
        return DataResult(status="unsupported", errors=["节点不支持条件查询"])

    def _read_semantic(self, query: str, top_k: int) -> DataResult:
        return DataResult(status="unsupported", errors=["节点不支持语义检索"])
