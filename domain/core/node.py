"""普通节点组合基础信息、模块、工具箱和出边。"""

from __future__ import annotations

from math import isfinite

from .aggregation import Aggregation, SumAggregation
from .installer import Installer
from .link import Links
from .module import Module, Modules
from .node_info import NodeInfo
from .tool import CallableTool, Tools


class Node:
    node_type = "node"

    def __init__(
        self, info: NodeInfo, *, aggregation: Aggregation | None = None, bias: float = 0,
    ) -> None:
        if aggregation is not None and not isinstance(aggregation, Aggregation):
            raise TypeError("汇合方法必须是 Aggregation 实例")
        self.info = info
        self.bias = bias
        self.aggregation = SumAggregation() if aggregation is None else aggregation
        self._resolve = None
        self._channel_names = None
        self._links = Links()
        self._modules = Modules()
        self._tools = Tools()
        self._installer = Installer(self._modules, self._tools, host=self)

    @property
    def bias(self) -> float:
        """接收强度在汇合后加上的偏置，负值表示衰减。"""
        return self._bias

    @bias.setter
    def bias(self, value: float) -> None:
        if type(value) not in (int, float) or not isfinite(value):
            raise ValueError("节点偏置必须是有限数值")
        self._bias = value

    @property
    def modules(self) -> Modules:
        return self._modules

    @property
    def tools(self) -> Tools:
        return self._tools

    @property
    def links(self) -> Links:
        return self._links

    def install(self, item: Module | CallableTool | Tools) -> None:
        self._installer.install(item)

    def remove(self, item: Module | str | CallableTool | Tools) -> bool:
        return self._installer.remove(item)
