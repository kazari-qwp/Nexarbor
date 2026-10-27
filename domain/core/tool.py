"""可执行工具与递归工具箱。"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .module import Module


@dataclass(eq=False)
class CallableTool:
    """一个可执行工具；按对象身份区分工具，不按字段内容比较。"""

    name: str
    function: Callable[..., Any]
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    modules: tuple[Module, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("工具名称必须是非空字符串")
        if not callable(self.function):
            raise TypeError("工具实现必须可调用")
        if not isinstance(self.description, str):
            raise TypeError("工具说明必须是字符串")
        if not isinstance(self.parameters, dict):
            raise TypeError("工具参数声明必须是字典")
        self.modules = tuple(self.modules)

    def invoke(self, **arguments: Any) -> Any:
        """调用实现；异步实现返回可等待对象，由调用方负责 await。"""
        return self.function(**arguments)


class Tools:
    """工具箱保存工具或子工具箱的引用；查询时递归展开，不复制成员。"""

    def __init__(self, members: Iterable[CallableTool | Tools] = ()) -> None:
        self._members: list[CallableTool | Tools] = []
        for member in members:
            self._add(member)

    @property
    def members(self) -> tuple[CallableTool | Tools, ...]:
        """当前工具箱的直接成员；挂载后的增删由安装管理器负责。"""
        return tuple(self._members)

    def _add(self, member: CallableTool | Tools) -> None:
        """添加直接成员；同一对象重复添加无效，循环包含会被拒绝。"""
        if not isinstance(member, (CallableTool, Tools)):
            raise TypeError("成员必须是可执行工具或工具箱")
        if isinstance(member, Tools) and member._contains_group(self):
            raise ValueError("工具箱不能形成循环包含")
        if not any(existing is member for existing in self._members):
            self._members.append(member)

    def _remove(self, member: CallableTool | Tools) -> bool:
        """按身份移除直接成员；返回是否移除，不销毁成员或搜索子工具箱。"""
        for index, existing in enumerate(self._members):
            if existing is member:
                del self._members[index]
                return True
        return False

    def __iter__(self) -> Iterator[CallableTool]:
        """按成员顺序递归遍历；相同对象去重，不同工具同名时报错。"""
        seen: dict[str, CallableTool] = {}
        for member in self._members:
            tools = member if isinstance(member, Tools) else (member,)
            for tool in tools:
                existing = seen.get(tool.name)
                if existing is tool:
                    continue
                if existing is not None:
                    raise ValueError(f"工具名称冲突：{tool.name}")
                seen[tool.name] = tool
                yield tool

    def list(self) -> list[CallableTool]:
        """将递归迭代的结果收集为列表。"""
        return list(self)

    def copy(self) -> Tools:
        """浅拷贝工具箱；保留成员引用，不展开子工具箱或检查依赖。"""
        copied = Tools()
        copied._members = self._members.copy()
        return copied

    def _contains_group(self, target: Tools) -> bool:
        if self is target:
            return True
        return any(
            isinstance(member, Tools) and member._contains_group(target)
            for member in self._members
        )
