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
                 config_schema=None, state_schema=None):
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
        self.signals = names(signals, 'signal channels')
        self.node_types = names(node_types, 'node types', allow_empty=False)
        if set(self.node_types) - {'node', 'text_file', 'agent', 'pulse'}:
            raise ValueError('Unknown component node type')
        self.config_schema = config_schema or {'type': 'object'}
        self.state_schema = state_schema or {'type': 'object'}
        for schema in (self.config_schema, self.state_schema): Draft202012Validator.check_schema(schema)

    def __call__(self, context):
        from .local_modules import NodeModule
        return NodeModule(context, self)

    def validate(self, value, schema): Draft202012Validator(schema).validate(thaw(value))


def require_definition(value):
    if type(value) is not ModuleDefinition:
        raise TypeError('Only ModuleDefinition with async execute(ctx, activation) may be registered; legacy modules are unsupported')
    return value
