"""只处理本次安装的依赖，以及本次移除是否会破坏依赖。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from .module import Module, Modules
from .tool import CallableTool, Tools

if TYPE_CHECKING:
    from .node import Node


class DependencyError(ValueError):
    """依赖成环，或待移除的模块仍被使用。"""


class Installer:
    """统一维护节点的两张表，信任已经通过管理器完成的装配。"""

    def __init__(
        self, modules: Modules | None = None, tools: Tools | None = None, *, host: Node | None = None,
    ) -> None:
        self._host = host
        self._modules = Modules() if modules is None else modules
        self._tools = Tools() if tools is None else tools
        self._tools._add(self._modules.tools)

    @property
    def modules(self) -> Modules:
        return self._modules

    @property
    def tools(self) -> Tools:
        return self._tools

    def install(self, item: Module | CallableTool | Tools) -> None:
        """先解析新增依赖，再安装目标；失败时撤销本次新增挂接。"""
        if not isinstance(item, (Module, CallableTool, Tools)):
            raise TypeError("只能安装模块、工具或工具箱")
        if isinstance(item, Module) and self._modules.get(item.module_id) is item:
            return
        if not isinstance(item, Module) and any(item is member for member in self._tools.members):
            return
        if isinstance(item, Tools) and item._contains_group(self._modules.tools):
            raise ValueError("节点的模块聚合工具箱不能作为普通工具箱安装")

        bound: list[Module] = []
        installed: list[Module] = []
        try:
            planned = self._plan(item, bound)
            incoming = [tool for module in planned for tool in module.tools]
            if not isinstance(item, Module):
                incoming.extend(item if isinstance(item, Tools) else (item,))
            names = {tool.name: tool for tool in self._tools}
            for tool in incoming:
                if names.setdefault(tool.name, tool) is not tool:
                    raise ValueError(f"工具名称冲突：{tool.name}")

            for module in planned:
                self._modules._add(module)
                installed.append(module)
            if not isinstance(item, Module):
                self._tools._add(item)
        except Exception:
            for module in reversed(installed):
                self._modules._remove(module.module_id)
            for module in reversed(bound):
                module._unbind()
            raise

    def remove(self, item: Module | str | CallableTool | Tools) -> bool:
        """移除目标并保留依赖；仍被保留对象依赖的模块禁止移除。"""
        if isinstance(item, (Module, str)):
            module_id = item.module_id if isinstance(item, Module) else item
            module = self._modules.get(module_id)
            if module is None:
                return False
            if isinstance(item, Module) and item is not module:
                raise ValueError(f"模块标识对应其他实例：{module_id}")
            self._check_remove(module)
            removed = self._modules._remove(module_id)
            if removed and self._host is not None:
                module._unbind()
            return removed
        if not isinstance(item, (CallableTool, Tools)):
            raise TypeError("只能移除模块、模块标识、工具或工具箱")
        if item is self._modules.tools:
            raise ValueError("请通过移除模块来维护模块聚合工具箱")
        return self._tools._remove(item)

    def _plan(self, item: Module | CallableTool | Tools, bound: list[Module]) -> list[Module]:
        """只遍历本次目标的新增依赖，已安装的模块直接复用。"""
        planned: dict[str, Module] = {}
        visiting: list[str] = []

        def visit(module: Module) -> None:
            if not isinstance(module, Module):
                raise TypeError("依赖声明必须包含 Module 实例")
            key = module.module_id
            existing = self._modules.get(key)
            if existing is None:
                existing = planned.get(key)
            if existing is not None:
                if existing is not module:
                    raise ValueError(f"模块标识冲突：{key}")
                return
            if key in visiting:
                raise DependencyError(f"模块循环依赖：{' -> '.join([*visiting, key])}")
            if self._host is not None:
                if module._access_origin is not None and module._access_origin is not self._host:
                    raise ValueError(f"模块已经安装到其他节点：{key}")
                bound.append(module)
                module._bind(self._host)
            visiting.append(key)
            for dependency in self._dependencies(module):
                visit(dependency)
            visiting.pop()
            planned[key] = module

        if isinstance(item, Module):
            visit(item)
        else:
            for dependency in self._dependencies(item):
                visit(dependency)
        return list(planned.values())

    @staticmethod
    def _dependencies(item: Module | CallableTool | Tools) -> Iterator[Module]:
        """合并模块自身声明和工具声明，跳过模块工具对其所属模块的引用。"""
        if isinstance(item, Module):
            yield from item.modules
            tools = item.tools
        else:
            tools = item if isinstance(item, Tools) else (item,)
        for tool in tools:
            for dependency in tool.modules:
                if not isinstance(item, Module) or dependency is not item:
                    yield dependency

    def _check_remove(self, removed: Module) -> None:
        """只检查移除后仍保留的模块和工具，不重新校验它们的依赖树。"""
        remaining = [module for module in self._modules if module is not removed]
        for module in remaining:
            if removed in module.modules:
                raise DependencyError(f"模块 {removed.module_id} 仍被模块 {module.module_id} 依赖")
        sources = [member for member in self._tools.members if member is not self._modules.tools]
        sources.extend(module.tools for module in remaining)
        for source in sources:
            tools = source if isinstance(source, Tools) else (source,)
            for tool in tools:
                if removed in tool.modules:
                    raise DependencyError(f"模块 {removed.module_id} 仍被工具 {tool.name} 依赖")
