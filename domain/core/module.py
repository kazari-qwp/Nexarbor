"""模块及模块容器；容器自动聚合其成员的工具箱。"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

from .access import _normalize_channels, _validate_strength
from .channel_filters import validate_mode
from .tool import CallableTool, Tools

if TYPE_CHECKING:
    from .node import Node


class Module:
    """一个模块实例，拥有稳定标识和独立工具箱，可由具体业务模块继承。"""

    def __init__(
        self,
        module_id: str,
        *,
        description: str = "",
        channels: str | Iterable[str] = (),
        strength: float = 1,
        channel_mode: str = "allow",
        modules: Iterable[Module] = (),
        tools: Iterable[CallableTool | Tools] = (),
    ) -> None:
        if not isinstance(module_id, str) or not module_id.strip():
            raise ValueError("模块标识必须是非空字符串")
        if not isinstance(description, str):
            raise TypeError("模块说明必须是字符串")
        self._module_id = module_id
        self.description = description
        self.channels = _normalize_channels(channels)
        self.strength = _validate_strength(strength)
        self.channel_mode = validate_mode(channel_mode)
        self._access_origin: Node | None = None
        self._dependencies = tuple(modules)
        self._tools = Tools(tools)

    def _bind(self, node: Node) -> None:
        """安装管理器绑定所属节点；跨节点操作统一使用 @access。"""
        self._access_origin = node

    def _unbind(self) -> None:
        self._access_origin = None

    @property
    def module_id(self) -> str:
        """稳定标识，用于模块容器的查询与移除。"""
        return self._module_id

    @property
    def tools(self) -> Tools:
        """工具箱引用固定；挂载后的增删由安装管理器负责。"""
        return self._tools

    @property
    def modules(self) -> tuple[Module, ...]:
        """依赖声明；实际安装位置是所属节点的模块表。"""
        return self._dependencies


class Modules:
    """按标识管理模块，并将模块的工具箱挂接到同一个聚合工具箱。"""

    def __init__(self) -> None:
        self._modules: dict[str, Module] = {}
        self._tools = Tools()

    @property
    def tools(self) -> Tools:
        """供节点工具箱持有的稳定入口，自动反映模块及其工具的变化。"""
        return self._tools

    def _add(self, module: Module) -> None:
        """安装管理器确认后，登记模块并挂接其工具箱。"""
        self._tools._add(module.tools)
        self._modules[module.module_id] = module

    def _remove(self, module_id: str) -> bool:
        """按标识移除模块并摘除其工具箱；返回是否移除。"""
        module = self._modules.get(module_id)
        if module is None:
            return False
        self._tools._remove(module.tools)
        del self._modules[module_id]
        return True

    def copy(self) -> Modules:
        """浅拷贝模块表及聚合工具箱；保留模块实例，不安装或检查依赖。"""
        copied = Modules()
        copied._modules = self._modules.copy()
        copied._tools = self._tools.copy()
        return copied

    def get(self, module_id: str) -> Module | None:
        """按标识查询模块，不存在时返回 None。"""
        return self._modules.get(module_id)

    def __iter__(self) -> Iterator[Module]:
        """按添加顺序遍历模块。"""
        return iter(self._modules.values())

    def __len__(self) -> int:
        return len(self._modules)
