"""数据访问结果；保留原状态、数据项、来源和错误字段。"""

from dataclasses import dataclass, field
from typing import Any

@dataclass
class DataResult:
    status: str = 'ok'
    items: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
