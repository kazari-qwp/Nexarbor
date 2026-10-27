"""节点汇合策略：合并同一遍历层的非空输入强度。"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from statistics import mean


class Aggregation(ABC):
    @abstractmethod
    def combine(self, strengths: Iterable[float]) -> float:
        pass


class SumAggregation(Aggregation):
    def combine(self, strengths: Iterable[float]) -> float:
        return sum(strengths)


class MaxAggregation(Aggregation):
    def combine(self, strengths: Iterable[float]) -> float:
        return max(strengths)


class MinAggregation(Aggregation):
    def combine(self, strengths: Iterable[float]) -> float:
        return min(strengths)


class AverageAggregation(Aggregation):
    def combine(self, strengths: Iterable[float]) -> float:
        return mean(strengths)
