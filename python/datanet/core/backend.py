from .resource_data import read_data,write_data,encode_bytes,decode_data
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
from datanet.core.serialization import save_network, load_network, network_document
from datanet.core.tool_access import list_nodes, list_tools, invoke_tool, attach_discovery_tools
from datanet.core.interface_management import attach_interface_management_tools
from .checkpoints import Checkpoints
from datanet.core.serialization import _build
from functools import partial
from threading import RLock
from .storage_paths import storage_path
from datanet.core.packages.network import load_network_package

class Backend:

    def __init__(self, directory, *, snapshot_interval=100,initial_document=None):
        self._transaction_lock = RLock()
        self._runtime = None
        self.directory = storage_path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.store = Checkpoints(self.directory,snapshot_interval=snapshot_interval)
        self.agents = {}
        self.failed = False
        self.commit_observer = None
        self.agent_executor = None
        self.context_port = None
        self.network = Network()
        from .node_locks import NodeLocks
        self.node_locks = NodeLocks(self)
        self.network.node_locks = self.node_locks
        self.metadata_registry = self.network.metadata_registry
        from datanet.core.agent_node import AgentNode
        self.root = AgentNode('root', 'DataNet根节点', file_path=self.directory / 'root-memory.md')
        self.network.add_node(self.root)
        self.extension_state = {}
        from .external_tools import ExternalTools
        self.external_tools = ExternalTools(self)
        self.components = ComponentServices()
        from .node_modules import NodeModules
        self.modules = NodeModules(self,self.components.module_types)
        try:
            self.components.install(self)
            previous = self.store.latest()
            if previous is not None:
                self.restore(previous)
            elif initial_document is not None:
                self.load_initial_document(initial_document)
            if previous is None:self.modules.restore()
            self.components.graph_loaded(self)
            self.attach_creation()
            attach_interface_management_tools(self.network, self.root, scope='descendants')
            if previous is None:
                self.store.commit(self.snapshot())
        except Exception:
            if self._runtime is not None:self._runtime.close()
            self.store.close()
            raise

    def load_initial_document(self,document):
        """Load a declarative initial graph only into a new, empty backend."""
        if set(self.network.nodes)!={'root'} or self.store.latest() is not None:raise ValueError('Initial config requires an empty backend')
        candidate=_build(document['network'],self.directory)
        if 'root' not in candidate.nodes:raise ValueError('Initial config requires root')
        self.network=candidate;candidate.use_metadata_registry(self.metadata_registry);self.root=candidate.nodes['root']
        candidate.node_locks = self.node_locks
        self.write_documents(document.get('files',{}))

    def write_documents(self,documents):
        """Track configuration-owned text resources with the graph checkpoints."""
        files=[]
        for name,text in documents.items():
            target=(self.directory/name).resolve()
            if not target.is_relative_to(self.directory):raise ValueError('Initial documents must stay in backend directory')
            decode_data(text)
            files.append((target,text))
        for target,text in files:write_data(target,text)
        self.extension_state['document_resources']=sorted(set(self.extension_state.get('document_resources',[]))|{target.relative_to(self.directory).as_posix() for target,_ in files})

    def document_files(self):
        files={}
        for name in self.extension_state.get('document_resources',[]):
            target=(self.directory/name).resolve()
            if not target.is_relative_to(self.directory):raise ValueError('Document escapes runtime directory')
            files[name]=read_data(target)
        return files

    @property
    def runtime(self):
        if self._runtime is None:
            from .async_runtime import AsyncRuntime
            with self._transaction_lock:
                if self._runtime is None:self._runtime = AsyncRuntime()
        return self._runtime

    @property
    def signals(self):
        runtime=self.network.signals
        async def checkpoint():
            await self.node_locks.wait_prepared()
            self.dispatch('save',{})
        runtime.checkpoint=checkpoint
        return runtime

    async def execute_agent(self,node_id,message='',**options):
        """Stable asynchronous port implemented by the selected host adapter."""
        if self.agent_executor is None:raise RuntimeError('This host has no Agent executor installed')
        return await self.agent_executor(node_id,message,**options)

    def close(self):
        if self._runtime is not None:self._runtime.close()
        try:
            self.modules.clear()
        finally:
            try:
                for close in reversed(self.components.finalizers):close(self)
            finally:self.store.close()

    def snapshot(self, *, committing=None):
        self.node_locks.wait_prepared_sync()
        with self._transaction_lock:
            return self._snapshot(committing=committing)

    def _snapshot(self, *, committing=None):
        from copy import deepcopy
        overrides, images = self.node_locks.overrides(committing)
        network = network_document(self.network,self.directory,node_overrides=overrides)
        files = self.document_files()
        # A locked directory publishes only its captured old files, including absent new files.
        for image in images.values():
            roots=image.get('resource_roots',[])
            files={name:value for name,value in files.items() if not any((self.directory/name).resolve()==p or kind=='directory' and (self.directory/name).resolve().is_relative_to(p) for _,p,kind in roots)}
        for node in self.network.nodes.values():
            if node.node_id in images: continue
            for _, label, target in resource_paths(node):
                if target.is_relative_to(self.directory):
                    files[target.relative_to(self.directory).as_posix()] = read_data(target)
        extra = {**self.extension_state, **self.components.snapshot(self)}
        files.update(extra.pop('files', {}))
        agents = deepcopy(self.agents)
        tools = {key: deepcopy(node.tool_definitions) for key, node in self.network.nodes.items()}
        tool_names = {key: list(node.tools) for key, node in self.network.nodes.items()}
        publications = {node: {} for node in self.network.nodes}
        for (node, module), fields in self.modules._published.items(): publications[node][module] = deepcopy(fields)
        for node, image in images.items():
            if image['binding'] is None: agents.pop(node, None)
            else: agents[node] = deepcopy(image['binding'])
            tools[node] = deepcopy(image['definitions']); tool_names[node] = list(image['tools'])
            publications[node] = {key[1]: deepcopy(fields) for key, fields in image['published'].items()}
            for path, content in image['files'].items():
                files[path.relative_to(self.directory).as_posix()] = encode_bytes(content)
        document = deepcopy({'version': 1, 'network': network, 'agents': agents, 'files': files,
                         'tool_names': tool_names, 'tools': tools, 'node_publications': publications, **extra})
        from .node_records import merge_records
        return merge_records(document,self.node_locks.records(committing))

    def capture_node_records(self, node_ids):
        """Trusted host: capture committed node records without chasing links."""
        from .node_records import capture_records
        with self._transaction_lock:
            files = {n:[p.relative_to(self.directory).as_posix() for _,_,p in resource_paths(self.network.nodes[n])
                        if p.is_relative_to(self.directory)] for n in node_ids}
            return capture_records(self.snapshot(),node_ids,files)

    async def capture_node_contexts(self, node_ids):
        bindings = {n:self.agents[n]['session_id'] for n in node_ids if self.agents.get(n,{}).get('session_id')}
        if not bindings:return {}
        if self.context_port is None:raise RuntimeError('Bound Agents require an executor context capture port before locking')
        cursors = await self.context_port.capture(bindings)
        if set(cursors) != set(bindings):raise ValueError('Executor cursor set does not match locked Agents')
        from .json_values import freeze,thaw
        cursors=thaw(freeze(cursors))
        for node,cursor in cursors.items():
            if not isinstance(cursor,dict) or cursor.get('session_id') != bindings[node]:
                raise ValueError('Executor session changed during node context capture')
        return cursors

    async def restore_node_contexts(self, cursors):
        if not cursors:return
        if self.context_port is None:raise RuntimeError('Executor context restore port is unavailable')
        result = await self.context_port.restore(cursors)
        if set(result.get('contexts',{})) != set(cursors):raise ValueError('Restored executor cursor set mismatch')
        for node,cursor in result['contexts'].items():
            if not isinstance(cursor,dict) or not isinstance(cursor.get('session_id'),str):raise ValueError('Invalid restored executor cursor')
            self.agents[node]['session_id']=cursor['session_id']
            self.network.nodes[node].context_cursor=cursor

    def commit_node_transaction(self, group):
        """Called under the coordinator mutex, before transaction gates reopen."""
        try:
            commit_id = self.store.commit(self.snapshot(committing=group))
        except BaseException:
            self.failed = True
            raise
        if self.commit_observer:
            try:self.commit_observer(commit_id)
            except Exception as error:self.notification_error=str(error)

    def restore(self, document):
        self.node_locks.lifecycle()
        if document.get('version') != 1:
            raise ValueError('Unsupported checkpoint version')
        self.extension_state = {k:v for k,v in document.items() if k not in {'version','network','agents','files','tool_names','tools','node_publications'}}
        self.network = _build(document['network'], self.directory)
        self.network.node_locks = self.node_locks
        self.network.use_metadata_registry(self.metadata_registry)
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
                    node.register_tool(name,inactive,description=definition['description'],parameters=definition['parameters'],access_channels=definition['access_channels'])
                for name in node.tools:node.tools[name]=inactive
        for name, content in document['files'].items():
            target = (self.directory / name).resolve()
            if not target.is_relative_to(self.directory):
                raise ValueError('Checkpoint file escapes runtime directory')
            write_data(target,content)

        self.modules.restore()
        for node, entries in document.get('node_publications', {}).items():
            for module, fields in entries.items():
                key = (node, module)
                if key in self.modules.instances:
                    self.modules._published[key] = fields
                    self.metadata_registry.register('module:' + repr(key), lambda target, key=key: self.modules._metadata_fields(key,target))
        from datanet.core.node_toolboxes import validate_exposure
        for node in self.network.nodes.values():validate_exposure(node)

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
        from datanet.core.agent_node import AgentNode
        if not isinstance(self.network.nodes[target],AgentNode):raise ValueError('Agents require an Agent node')
        for validate in self.components.binding_validators:validate(self,p)
        old = self.agents.get(target, {})
        manager_id = p.get('manager_id', old.get('manager_id', p.get('creator_node_id')))
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
        if method not in ('persistence_info','persistence_latest_point'):
            self.node_locks.wait_prepared_sync()
        from contextlib import nullcontext
        targets = []
        if method in ('agent_inputs_update','agent_inputs_ack','bind_agent','agent_progress'):
            targets = [p.get('target',p.get('actor'))]
        with self.node_locks.access_sync(targets) if targets else nullcontext():
            with self._transaction_lock:
                return self._dispatch_transaction(method, p)

    def _dispatch_transaction(self, method, p):
        if self.failed:
            raise RuntimeError('Checkpoint failed; restart before further operations')
        if method in {'network_structure','list_nodes','list_tools','invoke_tool','check_access'} and 'direction' in p:
            raise ValueError('direction 已移除；连接统一采用频道授权')
        if method in {'list_tools','invoke_tool'} and 'channels' in p:
            raise ValueError('工具访问频道由可信工具声明决定')
        mutation = method in self.components.mutations or method in {'invoke_tool', 'save', 'bind_agent', 'agent_progress', 'agent_inputs_update', 'agent_inputs_ack', 'network_initialize'}
        if not mutation:
            return self._dispatch(method, p)
        operation_id = uuid4().hex
        self.store.begin(operation_id, method)
        try:
            result = self._dispatch(method, p)
        except Exception:
            try:
                commit_id=self.store.commit(self.snapshot(),operation_id)
                if self.commit_observer:self.commit_observer(commit_id)
            except Exception:
                self.failed = True
            raise
        try:
            commit_id=self.store.commit(self.snapshot(), operation_id, force_snapshot=method=='save' and p.get('full',False))
            if self.commit_observer:self.commit_observer(commit_id)
        except Exception:
            self.failed = True
            raise
        return result

    def attach_creation(self, owner=None, options=None):
        owner = self.root if owner is None else owner
        options = {} if options is None else options
        attach_node_creation_tools(self.network, owner, storage_dir=self.directory / 'created', presets=self.components.node_presets, scope=options.get('scope', 'descendants'), allow_custom=options.get('allow_custom', False), network_presets=self.components.network_presets, toolkits=self.components.toolkits(self))

    def reachable_structure(self,actor,channels=(),depth=2,max_depth=100):
        from .json_values import names
        channels=names(channels,'channels')
        if type(depth) is not int or type(max_depth) is not int or max_depth<1 or not 0<=depth<=max_depth:raise ValueError('Invalid scan depth')
        nodes,links,_=self.network.routing_snapshot()
        layer,reached,edges,level=[actor],{actor},{},0
        while layer and (depth==max_depth or level<depth):
            following=[]
            for source in layer:
                targets=[]
                for link in links[source]:
                    if not set(channels).intersection(link.metadata.channels):continue
                    target=link.target_node_id
                    if target not in nodes:continue
                    if target not in targets:targets.append(target)
                    if target not in reached:reached.add(target);following.append(target)
                if targets:edges[source]=targets
            layer,level=following,level+1
        return dict(origin=actor,depth=depth,channels=list(channels),interfaces='\n'.join(source+' → '+', '.join(targets) for source,targets in edges.items()) or actor)

    def created_structure(self, report):
        """Describe only the newly created fragment and its attachment; no stored data."""
        ids = report['node_ids']
        nodes = []
        interfaces = []
        for local_id, node_id in ids.items():
            node = self.network.nodes[node_id]
            nodes.append({'local_id': local_id, **node.get_metadata(), 'type': type(node).__name__, 'exposed_tools': list(node.expose)})
            for index,link in enumerate(node.interfaces):
                interfaces.append({'source_node_id':node_id,'interface_index':index,**asdict(link)})
        parent_id = report['parent_node_id']
        parent = self.network.nodes[parent_id]
        created_ids = set(ids.values())
        attachment = [{'source_node_id':parent_id,'interface_index':index,**asdict(link)} for index,link in enumerate(parent.interfaces) if link.target_node_id in created_ids]
        return {'node_ids': ids, 'entry_points': report['entry_points'], 'parent_node_id': parent_id, 'nodes': nodes, 'interfaces': interfaces, 'attachment_interfaces': attachment}

    def _dispatch(self, method, p):
        if method == 'network_initialize':
            if set(self.network.nodes)!={'root'}:return {'loaded':False}
            self.restore(p['document'])
            self.components.graph_loaded(self)
            self.attach_creation()
            return {'loaded':True}
        if method == 'persistence_info':
            from .recovery import required_contexts
            return {**self.store.stats(),'pending':self.store.pending(),'executor_restore_required':required_contexts(self.store),'bindings':self.node_locks.committed_bindings(),**self.node_locks.context_status()}
        if method == 'persistence_points':return self.store.points()
        if method == 'persistence_checkpoint':
            contexts=p.get('contexts',{})
            self.node_locks.validate_contexts(contexts)
            bindings=self.node_locks.committed_bindings()
            if p.get('bindings')!=bindings or set(contexts)!=set(bindings):raise ValueError('Executor bindings changed during cursor capture')
            if type(p.get('expected_commit')) is not int:raise ValueError('Checkpoint requires an expected core commit')
            if p['expected_commit']!=self.store.head:raise RuntimeError('Network changed during executor cursor capture')
            for node,cursor in contexts.items():
                if node not in self.node_locks.exclusive:self.network.nodes[node].context_cursor=cursor
            self.store.commit(self.snapshot())
            return self.store.mark(contexts,p.get('kind','incremental'),self.store.head,reuse=True)
        if method == 'persistence_latest_point':
            row=self.store.db.execute('SELECT id FROM recovery_points ORDER BY rowid DESC LIMIT 1').fetchone()
            return self.store.point(row[0]) if row else None
        if method == 'persistence_mark':
            contexts=p.get('contexts',{})
            self.node_locks.validate_contexts(contexts)
            required=set(self.node_locks.committed_bindings())
            if set(contexts)!=required:raise ValueError('Executor cursors must cover exactly all bound Agents')
            return self.store.mark(contexts,p.get('kind','incremental'),p.get('expected_commit'))
        if method == 'persistence_export':return self.store.bundle(p['point_id'])
        if method == 'persistence_restore':
            from .recovery import restore_bundle
            return restore_bundle(self.store.bundle(p['point_id']),p['directory'],sessions=p.get('sessions'))
        if method == 'persistence_executor_restored':
            from .recovery import acknowledge_executors
            return acknowledge_executors(self,p['sessions'])
        if method == 'persistence_reconcile':
            self.store.reconcile(p['operation_id'],p['reason']);return {'ok':True}
        if method == 'recovery_info':
            return {'node_count': len(self.network.nodes), 'agents': self.agents, 'management': {key: node.management_parent_id for key, node in self.network.nodes.items()}, 'unassigned_management_nodes': [key for key, node in self.network.nodes.items() if key != self.root.node_id and node.management_parent_id is None], 'pending_operations': self.store.pending(), 'checkpoint_count': self.store.db.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0], **self.components.status(self)}
        if method in self.components.routes:
            return self.components.routes[method](self, p)
        if method in ('agent_inputs_update','agent_inputs_ack'):
            from datanet.core.agent_node import AgentNode
            node=self.network.nodes[p['target']]
            if not isinstance(node,AgentNode):raise TypeError('Input target requires an Agent node')
            if method=='agent_inputs_update':return node.inputs.update(p['source'],p['patch'])
            node.inputs.acknowledge(p['source'],p['event_id']);return {'ok':True}
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
                if scope == 'children' and (not any((x.target_node_id == p['target'] for x in owner.interfaces))):
                    return {'allowed': False}
            return {'allowed': any((node.node_id == p['target'] for node, _ in self.network.walk(owner.node_id, channels=p.get('channels',()), strength=p['strength'])))}
        if method == 'check_access':
            return {'allowed': any((node.node_id == p['target'] for node, _ in self.network.walk(p['actor'], channels=p.get('channels',()), strength=p.get('strength', 2))))}
        if method == 'ping':
            return {'ok': True, 'core': 'datanet', 'nodes': len(self.network.nodes)}
        if method == 'network_structure':
            return self.reachable_structure(p['actor'], p.get('channels',()), p.get('depth', 2), p.get('max_depth', 100))
        if method == 'list_nodes':
            return list_nodes(self.network,p['actor'],strength=p.get('strength',2),channels=p.get('channels',()))
        if method == 'list_tools':
            return list_tools(self.network, p['actor'], p['target'], strength=p.get('strength', 2))
        if method == 'invoke_tool':
            return invoke_tool(self.network, p['actor'], p['target'], p['tool'], p.get('arguments', {}), strength=p.get('strength', 2))
        if method == 'save':
            path = self.directory / 'network.json'
            save_network(self.network, path)
            return {'path': str(path)}
        raise ValueError('unknown method: ' + method)
