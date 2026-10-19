"""Fixed component ABI. JSON payloads carry data, never ambient authority."""
from dataclasses import dataclass, field
from inspect import iscoroutinefunction, signature, Parameter
from uuid import uuid4
from jsonschema import Draft202012Validator
from .json_values import freeze, thaw, names


@dataclass(frozen=True)
class Activation:
    kind: str
    operation: str
    parameters: object
    source: str
    request_id: str = field(default_factory=lambda: uuid4().hex)
    signal: object = None
    delivery: object = None

    def __post_init__(self):
        if self.kind not in ('access', 'signal'): raise ValueError('Invalid activation kind')
        object.__setattr__(self, 'parameters', freeze(self.parameters))


@dataclass(frozen=True)
class ComponentResult:
    status: str = 'ok'
    data: object = None
    error: object = None

    def __post_init__(self):
        if self.status not in ('ok', 'error'): raise ValueError('Result status must be ok or error')
        if self.status == 'ok' and self.error is not None: raise ValueError('Successful result cannot contain an error')
        if self.status == 'error' and not isinstance(self.error, str): raise ValueError('Error result requires a message')
        object.__setattr__(self, 'data', freeze(self.data))


class ModuleDefinition:
    """Registration accepts this definition, not arbitrary factories/classes."""
    def __init__(self, execute, *, operations=(), signals=(), node_types=('node', 'text_file', 'agent', 'pulse'),
                 config_schema=None, state_schema=None, tool_provider=None, agent_tools=()):
        if not iscoroutinefunction(execute): raise TypeError('Component entry must be async execute(ctx, activation)')
        params = list(signature(execute).parameters.values())
        if len(params) != 2 or [p.name for p in params] != ['ctx', 'activation'] or any(
                p.kind not in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
                or p.default is not Parameter.empty for p in params):
            raise TypeError('Component signature must be exactly execute(ctx, activation)')
        self.execute = execute
        self.operations = {}
        for raw in operations:
            spec = thaw(freeze(raw))
            if set(spec) != {'name', 'channels', 'parameters', 'result'}: raise ValueError('Invalid operation declaration')
            if not isinstance(spec['name'], str) or not spec['name'] or spec['name'] in self.operations:
                raise ValueError('Invalid or duplicate operation')
            names(spec['channels'], 'operation channels')
            for key in ('parameters', 'result'): Draft202012Validator.check_schema(spec[key])
            if spec['parameters'].get('type') != 'object': raise ValueError('Operation parameters must be an object')
            self.operations[spec['name']] = spec
        if isinstance(signals, dict):
            if set(signals) != {'config'} or not isinstance(signals['config'], str) or not signals['config']:
                raise ValueError('Signal binding must name a config field')
            self.signals = freeze(signals)
        else: self.signals = names(signals, 'signal channels')
        self.node_types = names(node_types, 'node types', allow_empty=False)
        if any(not name.isidentifier() or not name.isascii() for name in self.node_types):
            raise ValueError('Unknown component node type')
        self.config_schema = config_schema or {'type': 'object'}
        self.state_schema = state_schema or {'type': 'object'}
        for schema in (self.config_schema, self.state_schema): Draft202012Validator.check_schema(schema)
        self.tool_provider = None
        self.agent_tools={}
        for raw in agent_tools:
            tool=thaw(freeze(raw))
            if set(tool)!={'id','name','description','operation'} or any(not isinstance(v,str) or not v for v in tool.values()):raise ValueError('模块工具需要非空 id、name、description、operation')
            if tool['id'] in self.agent_tools or tool['operation'] not in self.operations:raise ValueError('模块工具重复或引用未声明操作')
            self.agent_tools[tool['id']]=freeze(tool)
        if self.agent_tools and tool_provider is not None:raise ValueError('静态工具与动态工具提供器不能同时声明')
        if tool_provider is not None:
            if not isinstance(tool_provider, dict) or set(tool_provider) != {'list', 'invoke'}:
                raise ValueError('Tool provider requires list and invoke operation names')
            if any(name not in self.operations for name in tool_provider.values()):
                raise ValueError('Tool provider operations must be declared')
            self.tool_provider = freeze(tool_provider)

    def __call__(self, context):
        from .local_modules import NodeModule
        return NodeModule(context, self)

    def validate(self, value, schema): Draft202012Validator(schema).validate(thaw(value))


def require_definition(value):
    if type(value) is not ModuleDefinition:
        raise TypeError('Only ModuleDefinition with async execute(ctx, activation) may be registered; legacy modules are unsupported')
    return value
