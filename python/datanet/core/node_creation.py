from datanet.core.component_registry import active_codecs as codecs
'仅显式拥有工具的 Agent 可以创建子节点；不会同时创建 Agent。'
from copy import copy, deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import re
import shutil
from threading import RLock
from uuid import uuid4
from datanet.core.node import NodeResult
from datanet.core.management import SCOPES, resolve_managed
from datanet.core.interface import Interface, metadata_schema
from datanet.core.serialization import _build, save_network
from datanet.core.packages.network import load_network_package

def attach_node_creation_tools(network, owner, *, storage_dir, presets=None, allow_custom=False, scope='self', network_presets=None, toolkits=None):
    """宿主指定预设、资源路径基目录、自定义开关；不自动装配到其他节点。

    presets: {id: {type, parameters, name?, data_kind?, description?, divergence?}}。
    自定义只是已有节点实现的配置，不执行 Python、不新建 SQL 表或向量索引。
    """
    if network.nodes.get(owner.node_id) is not owner:
        raise ValueError('工具所属节点必须已登记在网络中')
    if type(allow_custom) is not bool:
        raise TypeError('allow_custom 必须为 bool')
    if scope not in SCOPES:
        raise ValueError('scope 必须为 self、children 或 descendants')
    presets = deepcopy(presets or {})
    network_presets = {key: load_network_package(path) for key, path in (network_presets or {}).items()}
    storage_dir = Path(storage_dir).resolve()
    lock = RLock()

    def catalog():
        return NodeResult(items=[{'allow_custom': allow_custom, 'scope': scope, 'presets': deepcopy(presets), 'node_types': [{'type': kind, 'description': description, 'parameter_fields': deepcopy({k: c.parameter_fields for k, c in codecs().items()}[kind])} for kind, description in {k: c.description for k, c in codecs().items()}.items() if allow_custom or any((spec.get('type') == kind for spec in presets.values()))], 'network_presets': [{'id': key, 'description': package.description, 'entry_points': list(package.entry_points)} for key, package in network_presets.items()] if scope != 'self' else [], 'custom_parameter_fields': deepcopy({k: c.parameter_fields for k, c in codecs().items()}) if allow_custom else {}}])

    def resolve(parent_node_id, strength):
        try:
            return (resolve_managed(network, owner.node_id, parent_node_id, scope), None)
        except PermissionError as error:
            return (None, NodeResult(status='forbidden', errors=[str(error)]))

    def connection(target, value):
        if value is None:
            value = {'metadata': {'visibility': 'private'}}
        if not isinstance(value, dict) or set(value) != {'metadata'}:
            raise ValueError('接口必须包含 metadata 对象')
        return Interface(target_node_id=target, **value)

    def create_child_node(child_id, node_spec, read_interface=None, write_interface=None, parent_node_id=None, strength=0):
        with lock:
            folder = None
            child = None
            published = False
            read_link = write_link = None
            parent = None
            try:
                parent, error = resolve(parent_node_id, strength)
                if error is not None:
                    return error
                if not isinstance(child_id, str) or not re.fullmatch('[\\w-]+', child_id):
                    raise ValueError('child_id 只能包含文字、数字、下划线、连字符')
                node_id = parent.node_id + '/' + child_id
                if node_id in network.nodes:
                    return NodeResult(status='conflict', errors=[f'节点已存在：{node_id}'])
                if not isinstance(node_spec, dict):
                    raise TypeError('node_spec 必须为字典')
                if 'preset' in node_spec:
                    if set(node_spec) - {'preset', 'name', 'description'}:
                        raise ValueError('预设仅接受 preset；修改配置需要自定义权限')
                    key = node_spec['preset']
                    if not isinstance(key, str) or key not in presets:
                        raise ValueError('未登记的节点预设')
                    spec = {**deepcopy(presets[key]), **{k: v for k, v in node_spec.items() if k != 'preset'}}
                else:
                    if not allow_custom:
                        return NodeResult(status='forbidden', errors=['不允许自定义节点'])
                    spec = deepcopy(node_spec)
                allowed = {'type', 'parameters', 'name', 'data_kind', 'description', 'divergence', 'toolboxes', 'expose'}
                if set(spec) - allowed or not {'type', 'parameters'} <= spec.keys():
                    raise ValueError('节点需要 type、parameters；可选 name、data_kind、description、divergence、toolboxes、expose')
                if spec['type'] not in codecs():raise ValueError('Node component is disabled: '+spec['type'])
                read_link, write_link = (connection(node_id, read_interface), connection(node_id, write_interface))
                entry = {'type': spec['type'], 'node_id': node_id, 'name': spec.get('name', child_id), 'data_kind': spec.get('data_kind'), 'description': spec.get('description', ''), 'divergence': spec.get('divergence', -1), 'parameters': spec['parameters'], 'connections': {'read_interfaces': [], 'write_interfaces': []}, 'agent': None, 'toolboxes': spec.get('toolboxes', []), 'expose': spec.get('expose', [])}
                folder = storage_dir / uuid4().hex
                folder.mkdir(parents=True)
                fragment = _build({'version': 5, 'signals': {}, 'nodes': [entry], 'delegations': []}, folder)
                child = fragment.nodes[node_id]
                from datanet.core.node_toolboxes import validate_exposure
                validate_exposure(child)
                save_network(fragment, folder / 'node.json')
                attachment = {'parent_node_id': parent.node_id, 'child_node_id': node_id, 'read_interface': asdict(read_link), 'write_interface': asdict(write_link), 'management_parent_id': parent.node_id}
                (folder / 'attachment.json').write_text(json.dumps(attachment, ensure_ascii=False, indent=2), encoding='utf-8')
                child.management_parent_id = parent.node_id
                network.add_node(child)
                published = True
                parent.read_interfaces.append(read_link)
                parent.write_interfaces.append(write_link)
                return NodeResult(items=[{**child.describe(include_schema=False), 'configuration_path': str(folder / 'node.json'), 'attachment_path': str(folder / 'attachment.json'), 'read_interface': asdict(read_link), 'write_interface': asdict(write_link)}])
            except Exception as error:
                if published and network.nodes.get(child.node_id) is child:
                    network.nodes.pop(child.node_id)
                    if read_link in parent.read_interfaces:
                        parent.read_interfaces.remove(read_link)
                    if write_link in parent.write_interfaces:
                        parent.write_interfaces.remove(write_link)
                if folder is not None and folder.parent == storage_dir and folder.exists():
                    shutil.rmtree(folder)
                return NodeResult(status='error', errors=[str(error)])

    def create_network(preset, instance_id, entry_point, parent_node_id=None, read_interface=None, write_interface=None, strength=0, with_agents=False):
        with lock:
            folder = None
            report = None
            parent = None
            read_link = write_link = None
            added_grants = []
            try:
                if scope == 'self':
                    return NodeResult(status='forbidden', errors=['使用网络预设需要 children 或 descendants 创建范围'])
                if type(with_agents) is not bool:
                    raise TypeError('with_agents 必须为 bool')
                service = getattr(owner, '_agent_creation_service', None)
                if with_agents and ('create_agent' not in owner.agent_tool_definitions or service is None):
                    return NodeResult(status='forbidden', errors=['带Agent建网需要同时拥有创建Agent工具'])
                parent, error = resolve(parent_node_id, strength)
                if error is not None:
                    return error
                if not isinstance(preset, str) or preset not in network_presets:
                    raise ValueError('未登记的网络预设')
                if not isinstance(instance_id, str) or not re.fullmatch('[\\w-]+', instance_id):
                    raise ValueError('instance_id 只能包含文字、数字、下划线、连字符')
                package = network_presets[preset]
                if not isinstance(entry_point, str) or entry_point not in package.entry_points:
                    raise ValueError('网络预设入口不存在')
                prefix = instance_id
                read_link = connection(prefix + '/' + package.entry_points[entry_point], read_interface)
                write_link = connection(read_link.target_node_id, write_interface)
                folder = storage_dir / uuid4().hex
                folder.mkdir(parents=True)
                report = package.mount(network, prefix, toolkits=toolkits, storage_dir=folder / 'resources')
                roots = [node_id for node_id in report.node_ids.values() if network.nodes[node_id].management_parent_id is None]
                for node_id in roots:
                    network.nodes[node_id].management_parent_id = parent.node_id
                skipped = []
                configs = {}
                for node_id in report.node_ids.values():
                    node = network.nodes[node_id]
                    if node.agent_config is not None:
                        if with_agents:
                            configs[node_id] = deepcopy(node.agent_config)
                        else:
                            skipped.append(node_id)
                            node.agent_config = None
                if with_agents:
                    service(configs, folder)
                from datanet.core.network import Network
                fragment = Network()
                fragment.nodes = {key: copy(network.nodes[key]) for key in report.node_ids.values()}
                for node_id in roots:
                    fragment.nodes[node_id].management_parent_id = None
                fragment.delegation_permissions = {key: list(network.delegation_permissions[key]) for key in fragment.nodes if key in network.delegation_permissions}
                save_network(fragment, folder / 'network.json')
                attachment = {'parent_node_id': parent.node_id, 'entry_node_id': read_link.target_node_id, 'read_interface': asdict(read_link), 'write_interface': asdict(write_link), 'management_parent_id': parent.node_id}
                (folder / 'attachment.json').write_text(json.dumps(attachment, ensure_ascii=False, indent=2), encoding='utf-8')
                parent.read_interfaces.append(read_link)
                parent.write_interfaces.append(write_link)
                if configs:
                    grants = network.delegation_permissions.setdefault(owner.node_id, [])
                    for node_id in configs:
                        if node_id not in grants:
                            grants.append(node_id)
                            added_grants.append(node_id)
                return NodeResult(items=[{'node_ids': report.node_ids, 'entry_points': report.entry_points, 'parent_node_id': parent.node_id, 'configuration_path': str(folder / 'network.json'), 'attachment_path': str(folder / 'attachment.json'), 'agent_configuration_skipped': skipped, 'agents_created': list(configs)}])
            except Exception as error:
                if report is not None:
                    for node_id in report.node_ids.values():
                        network.nodes.pop(node_id, None)
                        network.delegation_permissions.pop(node_id, None)
                    if read_link in parent.read_interfaces:
                        parent.read_interfaces.remove(read_link)
                    if write_link in parent.write_interfaces:
                        parent.write_interfaces.remove(write_link)
                    for node_id in added_grants:
                        network.delegation_permissions[owner.node_id].remove(node_id)
                if folder is not None and folder.parent == storage_dir and folder.exists():
                    shutil.rmtree(folder)
                return NodeResult(status='forbidden' if isinstance(error, PermissionError) else 'error', errors=[str(error)])
    owner.register_agent_tool('list_node_presets', catalog, description='列出获准使用的节点预设、自定义开关及参数字段。', parameters={'type': 'object', 'properties': {}, 'additionalProperties': False})
    interface_schema = {'type': 'object', 'properties': {'metadata': metadata_schema()}, 'required': ['metadata'], 'additionalProperties': False}
    owner.register_agent_tool('create_child_node', create_child_node, description='在管理范围内的父节点下面创建子节点，不创建Agent。先查看 list_node_presets。默认父节点为自己，默认私有读写接口。', parameters={'type': 'object', 'properties': {'child_id': {'type': 'string'}, 'parent_node_id': {'type': 'string', 'description': '省略表示自己；按管理归属和工具箱scope授权，不要求普通写可达。'}, 'node_spec': {'type': 'object', 'description': '{preset:id} 或 {type,parameters,name?,data_kind?,description?,divergence?,toolboxes?,expose?}'}, 'read_interface': interface_schema, 'write_interface': deepcopy(interface_schema)}, 'required': ['child_id', 'node_spec'], 'additionalProperties': False})
    owner.register_agent_tool('create_network', create_network, description='使用登记网络预设搭建子网络；需要children或descendants范围。with_agents=true可按预设同时装配Agent，但必须拥有create_agent且配置获准。默认仅建节点；失败撤销本次创建。', parameters={'type': 'object', 'properties': {'preset': {'type': 'string'}, 'instance_id': {'type': 'string'}, 'entry_point': {'type': 'string'}, 'parent_node_id': {'type': 'string'}, 'with_agents': {'type': 'boolean', 'description': '默认false；true按网络预设装配所有Agent，需要创建Agent授权，提示词独立复制。'}, 'read_interface': deepcopy(interface_schema), 'write_interface': deepcopy(interface_schema)}, 'required': ['preset', 'instance_id', 'entry_point'], 'additionalProperties': False})
    return {name: deepcopy(owner.agent_tool_definitions[name]) for name in ('list_node_presets', 'create_child_node', 'create_network')}
