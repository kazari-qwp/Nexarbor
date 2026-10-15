from datanet.core.component_registry import reference_parameters, resource_paths
'网络拼图模板：展开成普通节点，通过现有接口拼接。'
from copy import deepcopy
from dataclasses import dataclass
import re
from pathlib import Path
import shutil
from datanet.core.network import Network
from datanet.core.execution import load_execution_package
from datanet.core.packages.common import read_manifest
from datanet.core.serialization import _build, _fields, _string, LINKS
from datanet.core.tool_access import attach_discovery_tools

@dataclass(frozen=True)
class MountedNodes:
    """装配报告，不是另一层可访问网络。值都是普通节点 ID。"""
    node_ids: dict[str, str]
    entry_points: dict[str, str]

class NetworkPackage:

    def __init__(self, path):
        self.path, self._document = read_manifest(path, 'network', ('kind', 'version', 'id', 'description', 'network', 'entry_points', 'toolkits'))
        _fields(self._document['network'], ('version', 'nodes', 'delegations'), '拼图结构')
        if not isinstance(self._document['network']['nodes'], list):
            raise ValueError('nodes 必须为列表')
        for label in ('entry_points', 'toolkits'):
            if not isinstance(self._document[label], dict):
                raise ValueError(f'{label} 必须为字典')
        network, report = self._prepare(None)
        for alias, target in self._document['entry_points'].items():
            _string(alias, '入口别名')
            if target not in report.node_ids:
                raise ValueError(f'入口节点不存在：{target}')
        for target, names in self._document['toolkits'].items():
            if target not in network.nodes or not isinstance(names, list):
                raise ValueError('工具箱必须绑定到包内节点，且名称为列表')
            for name in names:
                _string(name, '工具箱名称')
            if len(names) != len(set(names)):
                raise ValueError('同一节点的工具箱重复')

    @property
    def package_id(self):
        return self._document['id']

    @property
    def description(self):
        return self._document['description']

    @property
    def entry_points(self):
        return deepcopy(self._document['entry_points'])

    def _prepare(self, instance_id):
        if instance_id is not None and (not isinstance(instance_id, str) or not re.fullmatch('[\\w.-]+', instance_id) or instance_id in ('.', '..')):
            raise ValueError('实例编号只能包含文字、数字、下划线、点或连字符')
        document = deepcopy(self._document['network'])
        ids = {}
        for entry in document['nodes']:
            if not isinstance(entry, dict):
                raise ValueError('节点必须为字典')
            local_id = _string(entry.get('node_id'), 'node_id')
            if local_id in ids:
                raise ValueError(f'包内节点编号重复：{local_id}')
            ids[local_id] = f'{instance_id}/{local_id}' if instance_id is not None else local_id
        for entry in document['nodes']:
            local_id = entry['node_id']
            reference = entry.get('agent')
            if reference is not None:
                _fields(reference, ('package',), 'Agent 配置包引用')
                path = self.path.parent / _string(reference['package'], 'Agent 包路径')
                entry['agent'] = load_execution_package(path).configure(node_bindings={**ids, 'self': ids[local_id]})
            entry['node_id'] = ids[local_id]
            parent = entry.get('management_parent_id')
            if parent is not None:
                if not isinstance(parent, str) or parent not in ids:
                    raise ValueError('Package management parent must reference an internal node')
                entry['management_parent_id'] = ids[parent]
            reference_parameters(entry['type'], entry['parameters'], ids)
            _fields(entry.get('connections'), LINKS, '连接')
            for label in LINKS:
                targets = entry['connections'][label]
                if not isinstance(targets, list):
                    raise ValueError('连接必须为列表')
                for interface in targets:
                    _fields(interface, ('target_node_id', 'threshold', 'visibility', 'multiplier'), '接口')
                    target = interface['target_node_id']
                    if not isinstance(target, str) or target not in ids:
                        raise ValueError('拼图内部连接只能引用包内节点')
                    interface['target_node_id'] = ids[target]
        if not isinstance(document['delegations'], list):
            raise ValueError('delegations 必须为列表')
        for grant in document['delegations']:
            _fields(grant, ('source', 'target'), '委托许可')
            for label in ('source', 'target'):
                if not isinstance(grant[label], str) or grant[label] not in ids:
                    raise ValueError('拼图委托许可只能引用包内节点')
                grant[label] = ids[grant[label]]
        entries = {}
        for alias, target in self._document['entry_points'].items():
            if not isinstance(target, str) or target not in ids:
                raise ValueError(f'入口节点不存在：{target}')
            entries[alias] = ids[target]
        return (_build(document, self.path.parent), MountedNodes(ids, entries))

    def _factories(self, toolkits):
        registry = {} if toolkits is None else toolkits
        if not isinstance(registry, dict):
            raise TypeError('工具箱注册表必须是字典')
        required = {name for names in self._document['toolkits'].values() for name in names}
        missing = required - registry.keys()
        if missing:
            raise ValueError(f'工具箱实现未登记：{sorted(missing)}')
        if any((not callable(registry[name]) for name in required)):
            raise TypeError('工具箱实现必须可调用')
        return registry

    def _install(self, network, report, registry):
        for local_id, actual_id in report.node_ids.items():
            node = network.nodes[actual_id]
            if hasattr(node, 'bind_network'):
                node.bind_network(network)
            for name in self._document['toolkits'].get(local_id, []):
                registry[name](network, node)
            if node.agent_config is not None:
                attach_discovery_tools(network, node)
            from datanet.core.node_toolboxes import validate_exposure
            validate_exposure(node)

    @staticmethod
    def _materialize(network, storage_dir):
        """通用实例资源：复制文本模板和 Agent 文件，不修改组件包。"""
        if storage_dir is None:
            return
        storage_dir = Path(storage_dir).resolve()
        for node in network.nodes.values():
            folder = storage_dir / node.node_id.encode('utf-8').hex()
            resources = []
            resources.extend(resource_paths(node, writable=True))
            if node.agent_config is not None:
                for label in ('prompt_path', 'tools_path'):
                    source = node.agent_config[label]
                    if source is not None:
                        resources.append((node.agent_config, label, Path(source)))
            for holder, label, source in resources:
                target = folder / ('agent' if isinstance(holder, dict) else 'data') / source.name
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if source.exists():
                        shutil.copyfile(source, target)
                    elif isinstance(holder, dict):
                        raise FileNotFoundError(source)
                    else:
                        target.write_text('', encoding='utf-8')
                if isinstance(holder, dict):
                    holder[label] = str(target)
                else:
                    setattr(holder, label, target)

    def instantiate(self, *, instance_id=None, toolkits=None, storage_dir=None):
        """创建普通 Network；不请求模型，Agent 在工具装配后单独实例化。"""
        registry = self._factories(toolkits)
        network, report = self._prepare(instance_id)
        self._materialize(network, storage_dir)
        self._install(network, report, registry)
        return (network, report)

    def mount(self, network, instance_id, *, toolkits=None, storage_dir=None):
        """把拼图节点加入已有网络；拼接仍由节点的接口列表完成。"""
        if instance_id is None:
            raise ValueError('挂载拼图必须指定实例编号，以避免节点 ID 冲突')
        registry = self._factories(toolkits)
        fragment, report = self._prepare(instance_id)
        collisions = fragment.nodes.keys() & network.nodes.keys()
        if collisions:
            raise ValueError(f'节点编号冲突：{sorted(collisions)}')
        self._materialize(fragment, storage_dir)
        network.nodes.update(fragment.nodes)
        network.delegation_permissions.update(fragment.delegation_permissions)
        try:
            self._install(network, report, registry)
        except Exception:
            for node_id in fragment.nodes:
                network.nodes.pop(node_id)
            for node_id in fragment.delegation_permissions:
                network.delegation_permissions.pop(node_id)
            raise
        return report

def load_network_package(path):
    return NetworkPackage(path)
