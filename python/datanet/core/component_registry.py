"""Component contracts for node codecs, package resources and registered services."""
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
import json
import os

@dataclass
class NodeCodec:
    type_id: str
    node_class: type
    encode: object
    decode: object
    parameter_fields: list = field(default_factory=list)
    description: str = ''
    resources: tuple = ()
    references: dict = field(default_factory=dict)
    local_write: bool = True
    local_read: bool = True
    local_schema: bool = True
_codecs = {}
_owners = {}
_toolboxes = {}
_toolbox_owners = {}
_enabled = None
_loaded = False

def register_node(codec):
    if codec.type_id in _codecs:
        raise ValueError('Duplicate node codec: ' + codec.type_id)
    _codecs[codec.type_id] = codec

def component_root():
    configured = os.environ.get('DATANET_COMPONENT_ROOT')
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / 'components'

def manifests():
    root = component_root()
    for kind in ('tools', 'skills', 'network_presets', 'toolboxes', 'agent_presets', 'nodes'):
        for file in sorted((root / kind).glob('*/component.json')):
            value = json.loads(file.read_text(encoding='utf-8'))
            value['directory'] = file.parent
            yield value

def ensure_nodes():
    global _loaded
    if _loaded:
        return
    _loaded = True
    from datanet.core.node import Node
    register_node(NodeCodec('node', Node, lambda node, base: {}, lambda common, params, base: Node(*common), description='无本地数据的组织节点，用于连接节点和挂载工具。', local_read=False, local_schema=False))
    from datanet.core.agent_node import AgentNode
    register_node(NodeCodec('agent', AgentNode, lambda node, base: {'file_path': os.path.relpath(node.file_path, base), 'creation_options': node.creation_options}, lambda common, params, base: AgentNode(*common, file_path=base / params['file_path'], creation_options=params.get('creation_options')), parameter_fields=['file_path', 'creation_options'], description='Agent 节点，绑定独立会话与个人 Markdown 记忆。', resources=('file_path',), local_read=False, local_write=False, local_schema=False))
    for manifest in manifests():
        for module in manifest.get('python', {}).get('node_codecs', []):
            before=set(_codecs)
            import_module(module).register()
            for key in set(_codecs)-before:_owners[key]=manifest['id']
        for module in manifest.get('python',{}).get('toolbox_installers',[]):
            before=set(_toolboxes)
            import_module(module).register()
            for key in set(_toolboxes)-before:_toolbox_owners[key]=manifest['id']

def codecs():
    ensure_nodes()
    return _codecs

def codec_for_node(node):
    return next((codec for codec in codecs().values() if type(node) is codec.node_class))

def attach_local_tools(node):
    codec = codec_for_node(node)
    installer = getattr(node, 'install_local_tools', None)
    if installer:
        installer()
        return
    from datanet.core.read_request import request_schema
    from datanet.core.node import NodeResult
    if codec.local_read and getattr(node, 'delivery', 'plain') != 'resident' and 'read' not in node.tool_definitions:
        node.register_tool('read', lambda request: node.read(request), description='读取本节点。key 按主键读取，filter 按条件查询，semantic 语义检索；不支持的方法返回 unsupported。', parameters={'type': 'object', 'properties': {'request': request_schema()}, 'required': ['request'], 'additionalProperties': False}, read_only=True)
    if codec.local_schema and 'get_schema' not in node.tool_definitions:

        def schema():
            try:
                return node.get_schema()
            except (OSError, ValueError) as error:
                return NodeResult(status='error', errors=[str(error)])
        node.register_tool('get_schema', schema, description='查看本节点的字段、主键及类型结构，不读取记录值。', parameters={'type': 'object', 'properties': {}, 'additionalProperties': False}, read_only=True)

def reference_parameters(type_id, parameters, ids):
    for label, mode in codecs()[type_id].references.items():
        if label not in parameters:
            continue
        parameters[label] = [ids[x] for x in parameters[label]] if mode == 'many' else ids[parameters[label]]

def resource_paths(node, writable=False):
    result = []
    for label in codec_for_node(node).resources:
        field = getattr(type(node), label, None)
        if writable and isinstance(field, property) and (field.fset is None):
            continue
        result.append((node, label, getattr(node, label)))
    return result

def register_toolbox(name, installer):
    if name in _toolboxes:raise ValueError('Duplicate node toolbox: '+name)
    _toolboxes[name]=installer

def toolboxes():
    ensure_nodes()
    return {name: _guarded_installer(name, installer) for name, installer in _toolboxes.items()}

def _guarded_installer(name, installer):
    owner = _toolbox_owners.get(name)
    def install(node):
        previous = dict(node.tools)
        installer(node)
        for tool_name, function in list(node.tools.items()):
            if previous.get(tool_name) is function:
                continue
            def invoke(*args, _function=function, **kwargs):
                if owner is not None and owner not in enabled_components():
                    from datanet.core.node import NodeResult
                    return NodeResult(status='forbidden', errors=['Toolbox component is disabled: ' + owner])
                return _function(*args, **kwargs)
            node.tools[tool_name] = invoke
    return install

def enabled_components():
    global _enabled
    if _enabled is None:
        catalog={m['id']:m for m in manifests()}
        file=component_root()/'profile.json'
        profile=json.loads(file.read_text(encoding='utf-8')) if file.exists() else {}
        profile.update(json.loads(os.environ.get('DATANET_COMPONENT_PROFILE','{}')))
        _enabled={id for id,m in catalog.items() if profile.get(id,m.get('enabled',True))}
        while True:
            inactive={id for id in _enabled if any(dep not in _enabled for dep in catalog[id].get('requires',[]))}
            if not inactive:break
            _enabled.difference_update(inactive)
    return _enabled

def node_enabled(node):
    codec=codec_for_node(node)
    owner=_owners.get(codec.type_id)
    return owner is None or owner in enabled_components()

def active_codecs():
    return {key:codec for key,codec in codecs().items() if key not in _owners or _owners[key] in enabled_components()}
