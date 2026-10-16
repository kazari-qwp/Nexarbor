from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, TYPE_CHECKING
from copy import deepcopy
from datanet.core.interface import Interface

@dataclass
class NodeResult:
    status: str = 'ok'
    items: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)

class Node:
    signal_type = 'node'

    def __init__(self, node_id: str, name: str, data_kind: str | None, *, description: str='', divergence: int=-1):
        if not isinstance(description, str):
            raise TypeError('description 必须是字符串')
        self.node_id = node_id
        self.name = name
        self.data_kind = data_kind
        self.description = description
        self.divergence = divergence
        self.agent: Any = None
        self.agent_config: dict | None = None
        self.execution_binding: dict | None = None
        self.management_parent_id: str | None = None
        self.read_interfaces: list[Interface] = []
        self.write_interfaces: list[Interface] = []
        self.tools: dict[str, Callable[..., Any]] = {}
        self.tool_definitions: dict[str, dict] = {}
        self.modules: dict = {}
        self.toolboxes: list[str] = []
        self.expose: list[str] = []
        self.agent_tool_definitions: dict[str, dict] = {}

    def register_agent_tool(self, name, function, *, description, parameters):
        if not isinstance(name, str) or not name or (not callable(function)):
            raise ValueError('工具名称必须非空，工具必须可调用')
        if name in self.tool_definitions:
            raise ValueError('Agent 专用工具不能与公开工具重名')
        if not isinstance(parameters, dict) or parameters.get('type') != 'object':
            raise ValueError('工具参数定义必须为 object')
        definition = {'type': 'function', 'function': {'name': name, 'description': description, 'parameters': deepcopy(parameters)}}
        self.tools[name] = function
        self.agent_tool_definitions[name] = definition
        if self.agent is not None:
            self.agent.tool_definitions = [d for d in self.agent.tool_definitions if d['function']['name'] != name] + [deepcopy(definition)]

    def register_tool(self, name: str, function: Callable[..., Any], *, description: str, parameters: dict, read_only: bool=False) -> None:
        """应用显式声明可发现的能力；未声明只读的工具不能通过读连接调用。"""
        if not isinstance(name, str) or not name or (not callable(function)):
            raise ValueError('工具名称必须非空，工具必须可调用')
        if name in self.agent_tool_definitions:
            raise ValueError('公开工具不能与 Agent 专用工具重名')
        if type(read_only) is not bool:
            raise TypeError('read_only 必须为 bool')
        if not isinstance(parameters, dict) or parameters.get('type') != 'object':
            raise ValueError('工具参数定义必须为 object')
        self.tools[name] = function
        self.tool_definitions[name] = {'name': name, 'description': description, 'parameters': deepcopy(parameters), 'read_only': read_only}

    def get_schema(self) -> dict | None:
        return None

    @property
    def divergence(self):
        return self._divergence

    @divergence.setter
    def divergence(self, value):
        if type(value) is not int:
            raise TypeError('散度必须是整数')
        self._divergence = value

    @property
    def schema(self) -> dict | None:
        return self.get_schema()

    def standard_metadata(self) -> dict:
        return {'node_id': self.node_id, 'management_parent_id': self.management_parent_id, 'name': self.name, 'node_type': self.signal_type, 'data_kind': self.data_kind, 'description': self.description, 'divergence': self.divergence, 'has_agent': self.agent is not None}

    def get_metadata(self) -> dict:
        registry = getattr(self, '_metadata_registry', None)
        return registry.read(self) if registry else self.standard_metadata()

    def describe(self, *, include_schema: bool=True) -> dict:
        result = self.get_metadata()
        if include_schema:
            try:
                result['schema'] = self.get_schema()
            except (OSError, ValueError) as error:
                result.update(schema=None, schema_error=str(error))
        return result

    def read(self, request: dict) -> NodeResult:
        from datanet.core.read_request import validate_request
        request = validate_request(request)
        method = request['method']
        if method == 'key':
            return self._read_key(request['key'])
        if method == 'filter':
            return self._read_filter(request['filters'])
        return self._read_semantic(request['query'], request.get('top_k', 5))

    def _read_key(self, key: str) -> NodeResult:
        return NodeResult(status='unsupported', errors=['节点不支持主键读取'])

    def _read_filter(self, filters: dict[str, Any]) -> NodeResult:
        return NodeResult(status='unsupported', errors=['节点不支持条件查询'])

    def _read_semantic(self, query: str, top_k: int) -> NodeResult:
        return NodeResult(status='unsupported', errors=['节点不支持语义检索'])

    def invoke_tool(self, tool_name: str, /, **arguments) -> Any:
        if tool_name not in self.tools:
            raise ValueError(f'工具不存在：{tool_name}')
        return self.tools[tool_name](**arguments)

    def write(self, key: str, value: Any, *, mode: str='upsert') -> NodeResult:
        return NodeResult(status='unsupported', errors=['节点不支持本地写入'])
