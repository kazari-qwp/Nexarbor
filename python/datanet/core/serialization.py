from datanet.core.component_registry import codecs, codec_for_node
'JSON v8：节点、连接、Agent 创建配置和显式委托许可。'
import json
import math
import os
import tempfile
from pathlib import Path
from datanet.core.interface import Interface
from datanet.core.management import validate_management
from dataclasses import asdict
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.core.execution import encode_execution, decode_execution
LINKS = ('interfaces',)

def _string(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f'{label} 必须是非空字符串')
    return value

def _json_value(value):
    """拒绝会被 JSON 静默转换、丢失类型的信息。"""
    if type(value) is float and (not math.isfinite(value)):
        raise ValueError('JSON 不支持非有限数值')
    if value is None or type(value) in (str, bool, int, float):
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict and all((type(key) is str for key in value)):
        for item in value.values():
            _json_value(item)
        return
    raise ValueError('单值数据必须由 JSON 原生类型组成；不支持元组、对象或非字符串字典键')

def _path_string(path, base):
    try:
        return Path(os.path.relpath(path, base)).as_posix()
    except ValueError:
        return path.as_posix()

def network_document(network: Network, base: str | Path, *, node_overrides=None) -> dict:
    """Materialize the validated graph without writing an intermediate full file."""
    if node_overrides is None and hasattr(network,'node_locks'):
        node_overrides = network.node_locks.overrides()[0]
    path = Path(base).resolve() / 'network.json'
    if not getattr(network, 'archived_entries', None):
        validate_management(network)
    entries = []
    for node_id, node in network.nodes.items():
        if node_overrides and node_id in node_overrides:
            from copy import deepcopy
            entries.append(deepcopy(node_overrides[node_id])); continue
        if node_id != node.node_id:
            raise ValueError('网络注册编号与节点编号不一致')
        from datanet.core.dormant_node import DormantNode
        if type(node) not in [c.node_class for c in codecs().values()] and not isinstance(node, DormantNode):
            raise ValueError(f'不支持保存的节点类型：{type(node).__name__}')
        if isinstance(node, DormantNode) and path.parent != node.original_base:
            raise ValueError('Enable the node component before relocating its storage manifest')
        _string(node_id, 'node_id')
        _string(node.name, 'name')
        if not isinstance(node.description, str):
            raise ValueError('description 必须为字符串')
        if node.data_kind is not None:
            _string(node.data_kind, 'data_kind')
        parameters = {}
        parameters = codec_for_node(node).encode(node, path.parent)
        connections = {}
        for label in LINKS:
            targets = [interface.target_node_id for interface in getattr(node, label)]
            if any((target not in network.nodes and target not in getattr(network, 'archived_ids', set()) for target in targets)):
                raise ValueError(f'节点 {node_id} 的 {label} 含不存在的目标')
            connections[label] = [asdict(interface) for interface in getattr(node, label)]
        agent_config = encode_execution(node, path.parent)
        _json_value(agent_config)
        entries.append({'type': codec_for_node(node).type_id, 'node_id': node_id, 'name': node.name, 'description': node.description, 'management_parent_id': node.management_parent_id, 'divergence': node.divergence, 'data_kind': node.data_kind, 'parameters': parameters, 'connections': connections, 'agent': agent_config, 'modules': node.modules, 'offered_tools': node.offered_tools, 'toolboxes': node.toolboxes, 'expose': node.expose, 'execution': node.execution_binding, 'context_cursor': node.context_cursor, 'inputs': node.inputs.snapshot() if hasattr(node,'inputs') else getattr(node,'_saved_inputs',None)})
    if getattr(network, 'archived_entries', None):
        entries.extend(network.archived_entries())
    document = {'version': 8, 'signals': network.signal_runs, 'nodes': entries, 'delegations': [{'source': source, 'target': target} for source, targets in network.delegation_permissions.items() for target in targets]}
    _build(document, path.parent)
    return document

def save_network(network: Network, path: str | Path) -> None:
    path = Path(path).resolve()
    document = network_document(network, path.parent)
    content = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()

def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{label} 字段必须为：{', '.join(expected)}")

def _build(document, base):
    if not isinstance(document, dict) or type(document.get('version')) is not int or document['version'] != 8:
        raise ValueError('不支持的网络配置版本')
    _fields(document, ('version', 'nodes', 'delegations', 'signals'), '网络配置')
    if not isinstance(document['nodes'], list):
        raise ValueError('nodes 必须是列表')
    network = Network()
    for entry in document['nodes']:
        _fields({k: v for k, v in entry.items() if k not in ('modules', 'offered_tools', 'toolboxes', 'expose', 'management_parent_id', 'execution', 'inputs', 'context_cursor')}, ('type', 'node_id', 'name', 'data_kind', 'parameters', 'connections', 'description', 'divergence', 'agent'), '节点')
        node_id = _string(entry['node_id'], 'node_id')
        name = _string(entry['name'], 'name')
        kind = entry['data_kind']
        if kind is not None:
            _string(kind, 'data_kind')
        params = entry['parameters']
        node_type = _string(entry['type'], 'type')
        common = (node_id, name, kind)
        from datanet.core.component_registry import manifests, enabled_components
        from datanet.core.dormant_node import DormantNode
        # An optional replacement codec must not disable the ordinary core node
        # when that replacement was never loaded. Extension-only parameters still
        # require the owning component, and remain dormant while it is disabled.
        inactive = next((m['id'] for m in manifests() if m['id'] not in enabled_components()
                         and node_type in m.get('nodeTypes', [])
                         and not (node_type in m.get('replacesNodeTypes', []) and node_type in codecs()
                                  and codecs()[node_type].node_class.__module__.startswith('datanet.core.')
                                  and not (set(params) - set(codecs()[node_type].parameter_fields)))), None)
        if inactive:
            node = DormantNode(common, node_type, params, base, inactive)
        elif node_type not in codecs():
            raise ValueError('Unknown node type or missing component: ' + node_type)
        else:
            node = codecs()[node_type].decode(common, params, base)
        from .node_modules import validate_modules
        node.modules = validate_modules(entry.get('modules', {}))
        from .external_tools import validate_offers
        node.offered_tools = validate_offers(entry.get('offered_tools', []))
        node.management_parent_id = entry.get('management_parent_id')
        node.toolboxes = entry.get('toolboxes', [])
        node.expose = entry.get('expose', [])
        from datanet.core.node_toolboxes import attach_node_toolboxes
        attach_node_toolboxes(node)
        node.agent_config = decode_execution(entry['agent'], base)
        if node.agent_config is not None:
            from datanet.core.agent_node import AgentNode
            if not isinstance(node,AgentNode):raise ValueError('Agent configuration requires an Agent node')
        if entry.get('inputs') is not None:
            from datanet.core.agent_inputs import AgentInputs
            if hasattr(node,'inputs'):node.inputs=AgentInputs(entry['inputs'])
            elif isinstance(node,DormantNode):node._saved_inputs=entry['inputs']
            else:raise ValueError('Input state requires an Agent node')
        node.execution_binding = entry.get('execution')
        cursor = entry.get('context_cursor')
        if cursor is not None and not isinstance(cursor,dict):raise ValueError('Executor cursor must be an object')
        _json_value(cursor);node.context_cursor = cursor
        _json_value(node.execution_binding)
        description = entry['description']
        if not isinstance(description, str):
            raise ValueError('description 必须为字符串')
        node.description = description
        node.divergence = entry['divergence']
        network.add_node(node)
    for entry in document['nodes']:
        connections = entry['connections']
        _fields(connections, LINKS, '连接')
        node = network.nodes[entry['node_id']]
        for label, targets in connections.items():
            if not isinstance(targets, list):
                raise ValueError(f'{label} 必须是列表')
            for entry in targets:
                _fields(entry, ('target_node_id', 'metadata'), '接口')
                interface = Interface(**entry)
                if interface.target_node_id not in network.nodes:
                    # Node records can be restored independently of their targets.
                    # Validate the interface first, then drop a dangling reference.
                    continue
                getattr(node, label).append(interface)
    delegations = document['delegations']
    if not isinstance(delegations, list):
        raise ValueError('delegations 必须是列表')
    for grant in delegations:
        _fields(grant, ('source', 'target'), '委托许可')
        source, target = (_string(grant['source'], 'source'), _string(grant['target'], 'target'))
        if source not in network.nodes or target not in network.nodes:
            raise ValueError('委托许可引用不存在的节点')
        targets = network.delegation_permissions.setdefault(source, [])
        if target in targets:
            raise ValueError('委托许可重复')
        targets.append(target)
    from .signals import restore_records
    network.signal_runs = restore_records(document['signals'])
    validate_management(network)
    return network

def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'JSON 字段重复：{key}')
        result[key] = value
    return result

def _invalid_constant(value):
    raise ValueError(f'JSON 不支持数值：{value}')

def load_network(path: str | Path) -> Network:
    """相对数据路径以配置文件所在目录为基准；不访问实际存储内容。"""
    path = Path(path).resolve()
    with path.open(encoding='utf-8') as file:
        document = json.load(file, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    return _build(document, path.parent)
