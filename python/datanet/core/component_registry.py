"""Component contracts for node codecs, package resources and registered services."""
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
import json
import os
from functools import lru_cache

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
_replacement_types=set()

def register_node(codec):
    if codec.type_id in _codecs and codec.type_id not in _replacement_types:
        raise ValueError('Duplicate node codec: ' + codec.type_id)
    _codecs[codec.type_id] = codec

from datanet.component_catalog import component_root, discover, resolve, mount_paths

def manifests():
    yield from _manifest_catalog(str(component_root())).values()


@lru_cache(maxsize=8)
def _manifest_catalog(root):
    return discover(root)


def ensure_nodes():
    global _loaded
    if _loaded:
        return
    _loaded = True
    from datanet.core.node import Node
    register_node(NodeCodec('node', Node, lambda node, base: {}, lambda common, params, base: Node(*common), description='无本地数据的组织节点，用于连接节点和挂载工具。', local_read=False, local_schema=False))
    from datanet.core.text_node import TextFileNode
    def encode_text(node,base):
        return {'file_path':os.path.relpath(node.file_path,base),'max_chars':node.max_chars}
    def decode_text(common,params,base):
        if set(params)-{'file_path','max_chars'}:raise ValueError('Unsupported ordinary text parameter')
        return TextFileNode(*common,base/params['file_path'],max_chars=params.get('max_chars'))
    register_node(NodeCodec('text_file',TextFileNode,encode_text,decode_text,parameter_fields=['file_path','max_chars'],description='UTF-8 text file',resources=('file_path',)))
    from datanet.core.agent_node import AgentNode
    register_node(NodeCodec('agent',AgentNode,lambda node,base:{'file_path':os.path.relpath(node.file_path,base),'creation_options':node.creation_options},lambda common,p,base:AgentNode(*common,file_path=base/p['file_path'],creation_options=p.get('creation_options')),parameter_fields=['file_path','creation_options'],resources=('file_path',),local_read=False,local_write=False,local_schema=False))
    from datanet.core.pulse_node import PulseNode
    from datanet.core.json_values import thaw
    from dataclasses import asdict
    register_node(NodeCodec('pulse',PulseNode,
        lambda n,b:dict(channels=list(n.channels),strength=n.strength,content=thaw(n.content),signal_options=thaw(n.signal_options),state=n.state),
        lambda c,p,b:PulseNode(*c,**p),parameter_fields=['channels','strength','content','signal_options','state'],
        description='脉冲节点：按频道发出有限轮次信号，闭环返回并完成本轮处理后继续下一轮。',
        local_read=False,local_write=False,local_schema=False))
    catalog, order = mount_paths()
    for key in order:
        manifest = catalog[key]
        for module in manifest.get('python', {}).get('node_codecs', []):
            before=dict(_codecs)
            _replacement_types.update(manifest.get('replacesNodeTypes',[]))
            try:import_module(module).register()
            finally:_replacement_types.clear()
            for key,value in _codecs.items():
                if before.get(key) is not value:_owners[key]=manifest['id']
        for module in manifest.get('python',{}).get('toolbox_installers',[]):
            before=set(_toolboxes)
            import_module(module).register()
            for key in set(_toolboxes)-before:_toolbox_owners[key]=manifest['id']

def codecs():
    ensure_nodes()
    return _codecs

def codec_for_node(node):
    from datanet.core.dormant_node import DormantNode
    if isinstance(node, DormantNode):
        return NodeCodec(node.original_type, DormantNode, lambda n, base: n.original_parameters, None)
    return next((codec for codec in codecs().values() if type(node) is codec.node_class))

def attach_local_tools(node):
    codec = codec_for_node(node)
    installer = getattr(node, 'install_local_tools', None)
    if installer:
        installer()
        return
    from datanet.core.read_request import request_schema
    from datanet.core.node import NodeResult
    if codec.local_read and 'read' not in node.tool_definitions:
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
    result = {name: _guarded_installer(name, installer) for name, installer in _toolboxes.items()}
    for manifest in manifests():
        if manifest['id'] not in enabled_components() and manifest.get('python', {}).get('toolbox_installers'):
            name = manifest['id'].split('/')[-1]
            def install(node, owner=manifest['id']):
                from datanet.core.node import NodeResult
                for tool in set(node.expose) | set(node.tool_definitions):
                    old = node.tool_definitions.get(tool, {})
                    node.register_tool(tool, lambda **args: NodeResult(status='forbidden', errors=['Component is disabled: ' + owner]), description='Component disabled', parameters=old.get('parameters', {'type':'object'}), read_only=old.get('read_only', tool not in {'write', 'delete'}))
            result[name] = install
    return result

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
        _, order, _ = resolve()
        _enabled = set(order)
    return _enabled

def node_enabled(node):
    from datanet.core.dormant_node import DormantNode
    if isinstance(node, DormantNode):
        return False
    codec=codec_for_node(node)
    owner=_owners.get(codec.type_id)
    return owner is None or owner in enabled_components()

def active_codecs():
    return {key:codec for key,codec in codecs().items() if key not in _owners or _owners[key] in enabled_components()}


def resource_directory(source_file):
    source=Path(source_file).resolve()
    for parent in source.parents:
        declaration=parent/'component.json'
        if declaration.exists():
            manifest=json.loads(declaration.read_text(encoding='utf-8'))
            return (parent/manifest.get('resources','.')/source.relative_to(parent).parent).resolve()
    # Frozen loaders relocate modules; retain the manifest's source/resource mapping.
    if 'datanet' in source.parts:
        relative=Path(*source.parts[source.parts.index('datanet'):])
        for manifest in manifests():
            python_path=manifest.get('python',{}).get('path')
            if python_path and (manifest['implementation_directory']/python_path/relative).is_file():
                return (manifest['directory']/python_path/relative.parent).resolve()
    return source.parent
