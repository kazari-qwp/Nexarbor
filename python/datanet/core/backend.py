from datanet.core.component_registry import resource_paths, node_enabled
from .service_registry import ComponentServices
"""Persistent graph operations and component service dispatch."""
import json
import sys
from pathlib import Path
from dataclasses import asdict, is_dataclass
from uuid import uuid4
from datanet.core.network import Network
from datanet.core.management import can_manage
from datanet.core.node import Node
from datanet.core.node_creation import attach_node_creation_tools
from datanet.core.serialization import save_network, load_network
from datanet.core.tool_access import list_nodes, list_tools, invoke_tool, attach_discovery_tools
from datanet.core.interface_management import attach_interface_management_tools
from .checkpoints import Checkpoints
from datanet.core.serialization import _build
from functools import partial
from threading import RLock
from datanet.core.packages.network import load_network_package

class Backend:

    def __init__(self, directory):
        self._transaction_lock = RLock()
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.store = Checkpoints(self.directory)
        self.agents = {}
        self.failed = False
        self.network = Network()
        self.root = Node('root', 'DataNet根节点', None)
        self.network.add_node(self.root)
        self.extension_state = {}
        self.components = ComponentServices()
        try:
            self.components.install(self)
            previous = self.store.latest()
            if previous is not None:
                self.restore(previous)
            self.components.graph_loaded(self)
            self.attach_creation()
            attach_interface_management_tools(self.network, self.root, scope='descendants')
            if previous is None:
                self.store.commit(self.snapshot())
        except Exception:
            self.store.close()
            raise

    def close(self):
        self.store.close()

    def snapshot(self):
        path = self.directory / 'checkpoint-network.tmp.json'
        try:
            save_network(self.network, path)
            network = json.loads(path.read_text(encoding='utf-8'))
        finally:
            path.unlink(missing_ok=True)
        files = {}
        for node in self.network.nodes.values():
            for _, label, target in resource_paths(node):
                if target.is_relative_to(self.directory):
                    files[str(target.relative_to(self.directory))] = target.read_text(encoding='utf-8') if target.exists() else None
        extra = {**self.extension_state, **self.components.snapshot(self)}
        files.update(extra.pop('files', {}))
        return {'version': 1, 'network': network, 'agents': self.agents, 'files': files, 'tool_names': {key: list(node.tools) for key, node in self.network.nodes.items()}, 'tools': {key: node.tool_definitions for key, node in self.network.nodes.items()}, **extra}

    def restore(self, document):
        if document.get('version') != 1:
            raise ValueError('Unsupported checkpoint version')
        self.extension_state = {k:v for k,v in document.items() if k not in {'version','network','agents','files','tool_names','tools'}}
        self.network = _build(document['network'], self.directory)
        self.root = self.network.nodes['root']
        self.agents = document['agents']
        self._restore_agent_managers()
        self.components.restore(self, document)
        for node in self.network.nodes.values():
            if 'list_nodes' in document.get('tool_names', {}).get(node.node_id, []):
                attach_discovery_tools(self.network, node)
            self.components.restore_node(self, node, document)
            if not node_enabled(node):
                from datanet.core.node import NodeResult
                def inactive(*args,**kwargs):return NodeResult(status='forbidden',errors=['Node component is disabled'])
                node.read=inactive;node.write=inactive
                for name,definition in document.get('tools',{}).get(node.node_id,{}).items():
                    node.register_tool(name,inactive,description=definition['description'],parameters=definition['parameters'],read_only=definition.get('read_only',False))
                for name in node.tools:node.tools[name]=inactive
        from datanet.core.node_toolboxes import validate_exposure
        for node in self.network.nodes.values():
            validate_exposure(node)
        for name, content in document['files'].items():
            target = (self.directory / name).resolve()
            if not target.is_relative_to(self.directory):
                raise ValueError('Checkpoint file escapes runtime directory')
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + '.restore.tmp')
                temporary.write_text(content, encoding='utf-8')
                temporary.replace(target)

    def _restore_agent_managers(self):
        for node_id, binding in self.agents.items():
            binding.setdefault('manager_id', binding.get('creator_node_id'))
            binding['managed_ids'] = []
        for node_id, binding in self.agents.items():
            manager = self.agents.get(binding['manager_id'])
            if manager is not None:
                manager['managed_ids'].append(node_id)

    def _bind_agent(self, p):
        target = p['target']
        if target not in self.network.nodes:
            raise ValueError('Agent target does not exist')
        old = self.agents.get(target, {})
        manager_id = p.get('manager_id', old.get('manager_id', p.get('creator_node_id')))
        if target == 'root' and (p.get('kind') != 'root' or manager_id is not None or p.get('creator_node_id') is not None):
            raise ValueError('Root binding is reserved for the native root Agent')
        if manager_id is not None and manager_id not in self.agents:
            raise ValueError('Manager has no Agent binding')
        seen = {target}
        current = manager_id
        while current is not None:
            if current in seen:
                raise ValueError('Agent management contains a cycle')
            seen.add(current)
            current = self.agents[current].get('manager_id')
        binding = {**old, **p, 'manager_id': manager_id, 'managed_ids': list(old.get('managed_ids', []))}
        changed = {target: binding}
        if old.get('manager_id') != manager_id:
            previous = self.agents.get(old.get('manager_id'))
            if previous is not None:
                previous['managed_ids'] = [x for x in previous.get('managed_ids', []) if x != target]
                changed[old['manager_id']] = previous
        if manager_id is not None:
            manager = self.agents[manager_id]
            if target not in manager.get('managed_ids', []):
                manager['managed_ids'] = [*manager.get('managed_ids', []), target]
            changed[manager_id] = manager
        self.agents[target] = binding
        return {'ok': True, 'agents': changed}

    def dispatch(self, method, p):
        with self._transaction_lock:
            return self._dispatch_transaction(method, p)

    def _dispatch_transaction(self, method, p):
        if self.failed:
            raise RuntimeError('Checkpoint failed; restart before further operations')
        mutation = method in self.components.mutations or method in {'write', 'invoke_tool', 'save', 'bind_agent', 'agent_progress'}
        if not mutation:
            return self._dispatch(method, p)
        operation_id = uuid4().hex
        self.store.begin(operation_id, method)
        try:
            result = self._dispatch(method, p)
        except Exception:
            try:
                self.store.commit(self.snapshot())
            except Exception:
                self.failed = True
            raise
        try:
            self.store.commit(self.snapshot(), operation_id)
        except Exception:
            self.failed = True
            raise
        return result

    def attach_creation(self, owner=None, options=None):
        owner = self.root if owner is None else owner
        options = {} if options is None else options
        attach_node_creation_tools(self.network, owner, storage_dir=self.directory / 'created', presets=self.components.node_presets, scope=options.get('scope', 'descendants'), allow_custom=options.get('allow_custom', False), network_presets=self.components.network_presets, toolkits=self.components.toolkits(self))

    def reachable_structure(self, actor, direction='read', depth=2, max_depth=100, inspect_private=False):
        if direction not in ('read', 'write', 'both'):
            raise ValueError('Invalid direction')
        if type(depth) is not int or type(max_depth) is not int or max_depth < 1 or (not 0 <= depth <= max_depth):
            raise ValueError('Invalid scan depth')
        if type(inspect_private) is not bool:
            raise ValueError('Invalid topology grant')
        result = {'origin': actor, 'depth': depth}
        for label in ('read', 'write') if direction == 'both' else (direction,):
            layer, reached, edges, level = ([actor], {actor}, {}, 0)
            while layer and (depth == max_depth or level < depth):
                following = []
                for source in layer:
                    targets = []
                    for link in getattr(self.network.nodes[source], label + '_interfaces'):
                        if link.visibility == 'private' and source != actor and (not inspect_private):
                            continue
                        target = link.target_node_id
                        if target not in self.network.nodes:
                            continue
                        if target not in targets:
                            targets.append(target)
                        if target not in reached:
                            reached.add(target)
                            following.append(target)
                    if targets:
                        edges[source] = targets
                layer, level = (following, level + 1)
            result[label] = '\n'.join((source + ' → ' + ', '.join(targets) for source, targets in edges.items())) or actor
        return result

    def created_structure(self, report):
        """Describe only the newly created fragment and its attachment; no stored data."""
        ids = report['node_ids']
        nodes = []
        interfaces = []
        for local_id, node_id in ids.items():
            node = self.network.nodes[node_id]
            nodes.append({'local_id': local_id, 'node_id': node_id, 'type': type(node).__name__, 'name': node.name, 'description': node.description, 'data_kind': node.data_kind, 'divergence': node.divergence, 'management_parent_id': node.management_parent_id, 'exposed_tools': list(node.expose)})
            for direction in ('read', 'write'):
                for index, link in enumerate(getattr(node, direction + '_interfaces')):
                    interfaces.append({'source_node_id': node_id, 'direction': direction, 'interface_index': index, **asdict(link)})
        parent_id = report['parent_node_id']
        parent = self.network.nodes[parent_id]
        created_ids = set(ids.values())
        attachment = [{'source_node_id': parent_id, 'direction': direction, 'interface_index': index, **asdict(link)} for direction in ('read', 'write') for index, link in enumerate(getattr(parent, direction + '_interfaces')) if link.target_node_id in created_ids]
        return {'node_ids': ids, 'entry_points': report['entry_points'], 'parent_node_id': parent_id, 'nodes': nodes, 'interfaces': interfaces, 'attachment_interfaces': attachment}

    def _dispatch(self, method, p):
        if method == 'recovery_info':
            return {'node_count': len(self.network.nodes), 'agents': self.agents, 'groups': {}, 'feedback': [], 'management': {key: node.management_parent_id for key, node in self.network.nodes.items()}, 'unassigned_management_nodes': [key for key, node in self.network.nodes.items() if key != self.root.node_id and node.management_parent_id is None], 'pending_operations': self.store.pending(), 'checkpoint_count': self.store.db.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0], **self.components.status(self)}
        if method in self.components.routes:
            return self.components.routes[method](self, p)
        if method == 'root_network_info':
            return {'root_node_id': self.root.node_id, 'agent_config': self.root.agent_config}
        if method == 'bind_agent':
            return self._bind_agent(p)
        if method == 'agent_progress':
            self.agents[p['target']].update(p)
            return {'ok': True}
        if method == 'check_management':
            return {'allowed': can_manage(self.network, p['actor'], p['target'], p['scope'])}
        if method == 'check_delegation':
            owner = self.network.nodes[p['actor']]
            scope = p['scope']
            if scope not in ('self', 'children', 'reachable'):
                raise ValueError('Invalid delegation scope')
            if p['target'] != owner.node_id:
                if scope == 'self':
                    return {'allowed': False}
                if scope == 'children' and (not any((x.target_node_id == p['target'] for x in owner.read_interfaces))):
                    return {'allowed': False}
            return {'allowed': any((node.node_id == p['target'] for node, _ in self.network.walk(owner.node_id, direction='read', strength=p['strength'])))}
        if method == 'check_access':
            return {'allowed': any((node.node_id == p['target'] for node, _ in self.network.walk(p['actor'], direction=p.get('direction', 'read'), strength=p.get('strength', 2))))}
        if method == 'ping':
            return {'ok': True, 'core': 'datanet', 'nodes': len(self.network.nodes)}
        if method == 'network_structure':
            return self.reachable_structure(p['actor'], p.get('direction', 'read'), p.get('depth', 2), p.get('max_depth', 100), p.get('inspect_private', False))
        if method == 'list_nodes':
            return list_nodes(self.network, p['actor'], strength=p.get('strength', 2))
        if method == 'list_tools':
            return list_tools(self.network, p['actor'], p['target'], strength=p.get('strength', 2), direction=p.get('direction', 'read'))
        if method == 'invoke_tool':
            return invoke_tool(self.network, p['actor'], p['target'], p['tool'], p.get('arguments', {}), strength=p.get('strength', 2), direction=p.get('direction', 'read'))
        if method == 'read':
            if p.get('target'):
                from datanet.core.access_budget import access_context
                from datanet.core.node import NodeResult
                for node, path, remaining in self.network.walk_states(p['actor'], strength=p.get('strength', 2), scope=p.get('scope', 'network')):
                    if node.node_id == p['target']:
                        with access_context(self.network, node.node_id, remaining, path):
                            return node.read(p['request'])
                return NodeResult(status='forbidden', errors=['Target is not readable from origin'])
            return self.network.read(p['actor'], p.get('request', {'method': 'key', 'key': 'content'}), strength=p.get('strength', 2), scope=p.get('scope', 'network'))
        if method == 'write':
            return self.network.write(p['actor'], p['target'], p['key'], p['value'], strength=p.get('strength', 2), mode=p.get('mode', 'upsert'))
        if method == 'save':
            path = self.directory / 'network.json'
            save_network(self.network, path)
            return {'path': str(path)}
        raise ValueError('unknown method: ' + method)
