"""Exclusive node transactions and shared admission for trusted core operations.

The short coordinator mutex is never held across an await. A transaction owns a
before-image while callbacks continue on other nodes; checkpoints overlay that
image until the entire group commits. Ownership belongs to a live call tree.
"""
import asyncio
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from threading import Condition,current_thread
import time

_owner = ContextVar('node_access_owner', default=None)
_transaction = ContextVar('node_transaction', default=None)
_access_stack = ContextVar('node_access_stack', default=())


def require_transaction_node(node_id):
    group = _transaction.get()
    if group and group.phase == 'active' and node_id not in group.nodes:
        raise PermissionError('Mutable component state must belong to the locked node group')


class NodeBusyError(RuntimeError):
    """A synchronous event-loop caller must use an asynchronous access port."""


class NodeLockDeadlockError(RuntimeError):
    """A call tree must abort instead of waiting on a dependency cycle."""


@dataclass(eq=False)
class _Owner:
    live: bool = True


@dataclass(eq=False)
class _Group:
    owner: object
    nodes: tuple
    executor: object = None
    images: dict = field(default_factory=dict)
    entries: dict = field(default_factory=dict)
    records: dict = field(default_factory=dict)
    contexts: dict = field(default_factory=dict)
    phase: str = 'preparing'
    rollback_only: bool = False
    depth: int = 1


class NodeLocks:
    def __init__(self, backend):
        self.backend = backend
        self.condition = Condition(backend._transaction_lock)
        self.exclusive, self.active = {}, {}
        self.waiters = set()
        self.tickets = {}
        self.dependencies = {}
        self.leases = {}

    @contextmanager
    def export_owner(self, actor):
        """Trusted adapter bridge; never a component parameter or graph grant."""
        from uuid import uuid4
        owner,token=self._identity();ticket=uuid4().hex
        with self.condition:self.tickets[ticket]=(owner,actor,self.current,_access_stack.get())
        try:yield ticket
        finally:
            with self.condition:self.tickets.pop(ticket,None)
            if token is not None:owner.live=False;_owner.reset(token)

    @contextmanager
    def import_owner(self, ticket, actor):
        if ticket is None:
            yield;return
        with self.condition:
            record=self.tickets.get(ticket)
            if not record or record[1]!=actor or not record[0].live:
                raise PermissionError('Executor node access ticket has expired')
            owner,_,group,stack=record
            if group is not None and group.phase!='active':raise PermissionError('Executor transaction has ended')
        token=_owner.set(owner);transaction_token=_transaction.set(group);stack_token=_access_stack.set(stack)
        try:yield
        finally:_access_stack.reset(stack_token);_transaction.reset(transaction_token);_owner.reset(token)

    @property
    def current(self):
        group = _transaction.get()
        return group if group and group.phase == 'active' else None

    def _check(self):
        if getattr(self.backend, 'failed', False):
            raise RuntimeError('Core state is unavailable; restart before further operations')

    def _notify(self):
        self.condition.notify_all()
        for loop, future in tuple(self.waiters):
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._wake, future)

    @staticmethod
    def _wake(future):
        if not future.done(): future.set_result(None)

    def _blocked(self, nodes, owner):
        return any(n in self.exclusive and self.exclusive[n] is not self.current for n in nodes)

    def _drained(self, nodes, owner):
        ancestors=set(_access_stack.get())
        return not self._blocked(nodes, owner) and not any(
            any(lease not in ancestors for lease in self.leases.get(n,{})) for n in nodes)

    @staticmethod
    def _executor():
        try:return asyncio.current_task()
        except RuntimeError:return current_thread()

    def _waiting_executor(self):
        # Awaited access tasks and adapter callbacks are descendants of the
        # transaction holder. Their waits therefore block that whole group.
        group=self.current
        return group.executor if group else self._executor()

    def _dependencies(self, nodes, drain, ancestors, waiting_group):
        blocked=set()
        for node in nodes:
            group=self.exclusive.get(node)
            if group and group is not waiting_group:blocked.add(group.executor)
            if drain:blocked.update(executor for lease,(_,executor) in self.leases.get(node,{}).items() if lease not in ancestors)
        return blocked

    def _detect_cycle(self, owner):
        graph={}
        for who,nodes,drain,ancestors,waiting_group in self.dependencies.values():
            graph.setdefault(who,set()).update(self._dependencies(nodes,drain,ancestors,waiting_group))
        def visit(who,seen):
            if who is owner:return True
            if who in seen:return False
            return any(visit(other,seen|{who}) for other in graph.get(who,set()))
        if any(visit(other,set()) for other in graph.get(owner,set())):
            raise NodeLockDeadlockError('Node lock dependency cycle; retry the whole operation')

    async def _wait(self, predicate, deadline, *, owner=None, nodes=(), drain=False):
        loop = asyncio.get_running_loop()
        while True:
            with self.condition:
                self._check()
                if predicate(): return
                left = deadline - time.monotonic()
                if left <= 0: raise TimeoutError('Node lock deadline exceeded')
                future = loop.create_future(); waiter = (loop, future)
                if owner is not None:
                    identity=self._waiting_executor()
                    self.dependencies[future]=(identity,nodes,drain,set(_access_stack.get()),self.current)
                    try:self._detect_cycle(identity)
                    except BaseException:
                        self.dependencies.pop(future,None);raise
                self.waiters.add(waiter)
            try: await asyncio.wait_for(future, left)
            finally:
                with self.condition:
                    self.waiters.discard(waiter)
                    self.dependencies.pop(future,None)

    def _identity(self):
        current = _owner.get()
        if current is not None and current.live: return current, None
        current = _Owner()
        return current, _owner.set(current)

    def _leave(self, nodes, owner, token, lease, stack_token):
        with self.condition:
            for n in nodes:
                self.leases[n].pop(lease)
                if not self.leases[n]:del self.leases[n]
                counts = self.active[n]; counts[owner] -= 1
                if not counts[owner]: del counts[owner]
                if not counts: del self.active[n]
            self._notify()
        _access_stack.reset(stack_token)
        if token is not None:
            owner.live = False; _owner.reset(token)

    def _admit(self, nodes, owner, mutable):
        self._check()
        group = self.current
        if group and mutable and not set(nodes) <= set(group.nodes):
            raise PermissionError('Transactional execution can modify only locked nodes')
        for n in nodes:
            if n not in self.backend.network.nodes: raise KeyError(n)
        lease=object()
        for n in nodes:
            counts = self.active.setdefault(n, {})
            counts[owner] = counts.get(owner, 0) + 1
            self.leases.setdefault(n,{})[lease]=(owner,self._executor())
        return lease,_access_stack.set((*_access_stack.get(),lease))

    @asynccontextmanager
    async def access(self, nodes, *, mutable=True, timeout=180):
        nodes = tuple(dict.fromkeys(nodes)); owner, token = self._identity()
        admitted = False; deadline = time.monotonic() + timeout
        try:
            while True:
                await self._wait(lambda: not self._blocked(nodes, owner), deadline,owner=owner,nodes=nodes)
                with self.condition:
                    if self._blocked(nodes, owner): continue
                    lease,stack_token=self._admit(nodes, owner, mutable); admitted = True; break
            yield
        finally:
            if admitted: self._leave(nodes, owner, token,lease,stack_token)
            elif token is not None:
                owner.live = False; _owner.reset(token)

    @contextmanager
    def access_sync(self, nodes, *, mutable=True, timeout=180):
        nodes = tuple(dict.fromkeys(nodes)); owner, token = self._identity()
        admitted = False; deadline = time.monotonic() + timeout
        try:
            with self.condition:
                while self._blocked(nodes, owner):
                    try: asyncio.get_running_loop()
                    except RuntimeError: pass
                    else: raise NodeBusyError('Use async node access while another transaction owns this node')
                    left = deadline - time.monotonic()
                    if left <= 0: raise TimeoutError('Node lock deadline exceeded')
                    waiting=object();identity=self._waiting_executor()
                    self.dependencies[waiting]=(identity,nodes,False,set(_access_stack.get()),self.current)
                    try:self._detect_cycle(identity);self.condition.wait(left)
                    finally:self.dependencies.pop(waiting,None)
                    self._check()
                lease,stack_token=self._admit(nodes, owner, mutable); admitted = True
            yield
        finally:
            if admitted: self._leave(nodes, owner, token,lease,stack_token)
            elif token is not None:
                owner.live = False; _owner.reset(token)

    def transaction(self, actor, nodes, *, strength=0, channels=(), timeout=30, validate=None, finish=None):
        if not isinstance(nodes, (list, tuple)) or not nodes or any(not isinstance(n, str) or not n for n in nodes):
            raise ValueError('Lock a nonempty list of node IDs')
        if type(timeout) not in (int, float) or not 0 < timeout <= 300:
            raise ValueError('Lock timeout must be between 0 and 300 seconds')
        from .interface import validate_strength
        from .json_values import names
        validate_strength(strength); channels = names(channels, 'lock channels')
        nodes = tuple(sorted(set(nodes)))
        def authorized():
            self._check()
            if validate: validate()
            reached = {n.node_id for n, _, _ in self.backend.network.walk_states(actor, strength=strength, channels=channels)}
            if not set(nodes) <= reached: raise PermissionError('Lock target is outside the current graph view')
        return NodeLockScope(self, nodes, authorized, timeout, finish)

    def _capture(self, group):
        backend = self.backend
        if hasattr(backend, 'snapshot'):
            document = backend.snapshot()
            group.entries = {e['node_id']: deepcopy(e) for e in document['network']['nodes'] if e['node_id'] in group.nodes}
        for node_id in group.nodes:
            node = backend.network.nodes[node_id]
            image = dict(attrs={name: deepcopy(getattr(node, name)) for name in (
                'name', 'description', 'data_kind', 'divergence', 'management_parent_id',
                'interfaces', 'modules', 'offered_tools', 'toolboxes', 'expose', 'agent_config', 'execution_binding','context_cursor')},
                tools=dict(node.tools), definitions=deepcopy(node.tool_definitions),
                agent_definitions=deepcopy(node.agent_tool_definitions), refusals=dict(node.tool_refusals),
                inputs=node.inputs.snapshot() if hasattr(node, 'inputs') else None,
                binding=deepcopy(getattr(backend, 'agents', {}).get(node_id)), files={}, published={})
            modules = getattr(backend, 'modules', None)
            if modules:
                image['published'] = {key: deepcopy(value) for key, value in modules._published.items() if key[0] == node_id}
            if hasattr(backend, 'directory'):
                from .component_registry import resource_paths,codec_for_node
                for name in codec_for_node(node).parameter_fields:
                    if hasattr(node,name) and name not in image['attrs']:
                        value=getattr(node,name)
                        try:image['attrs'][name]=deepcopy(value)
                        except TypeError:image['attrs'][name]=value  # immutable frozen JSON
                for _, _, path in resource_paths(node):
                    path = Path(path).resolve()
                    if not path.is_relative_to(backend.directory.resolve()):
                        raise ValueError('Transactional node resources must stay in the backend directory')
                    if path.exists() and not path.is_file():
                        raise ValueError('Directory-backed nodes need a transactional resource adapter')
                    image['files'][path] = path.read_bytes() if path.exists() else None
                for other in backend.network.nodes.values():
                    if other.node_id in group.nodes:continue
                    if any(Path(path).resolve() in image['files'] for _,_,path in resource_paths(other)):
                        raise ValueError('Nodes sharing a resource file must be locked together')
            group.images[node_id] = image
        if hasattr(backend,'snapshot'):
            from .node_records import capture_records
            files={n:[p.relative_to(backend.directory).as_posix() for p in image['files']] for n,image in group.images.items()}
            group.records=capture_records(document,group.nodes,files)

    def records(self, committing=None):
        result={}
        for group in set(self.exclusive.values()):
            if group is not committing:result.update(group.records)
        return result

    def _prepared(self):
        return not any(g.phase=='capturing_contexts' for g in set(self.exclusive.values()))

    async def wait_prepared(self):
        await self._wait(self._prepared,time.monotonic()+180)

    def wait_prepared_sync(self):
        with self.condition:
            while not self._prepared():
                try:asyncio.get_running_loop()
                except RuntimeError:pass
                else:raise NodeBusyError('Await node_locks.wait_prepared() before synchronous checkpointing')
                self.condition.wait();self._check()

    def context_status(self):
        with self.condition:
            contexts={}
            for group in set(self.exclusive.values()):contexts.update(deepcopy(group.contexts))
            return dict(node_locks_preparing=not self._prepared(),locked_contexts=contexts)

    def committed_bindings(self):
        agents=dict(getattr(self.backend,'agents',{}))
        for group in set(self.exclusive.values()):
            for node,image in group.images.items():
                if image['binding'] is None:agents.pop(node,None)
                else:agents[node]=image['binding']
        return {node:value['session_id'] for node,value in agents.items() if value.get('session_id')}

    def validate_contexts(self, contexts):
        status=self.context_status()
        if status['node_locks_preparing']:raise RuntimeError('Network changed during node cursor preparation')
        for node,cursor in status['locked_contexts'].items():
            if contexts.get(node)!=cursor:raise RuntimeError('Network changed during locked executor cursor capture')

    def _restore(self, group):
        backend = self.backend
        for node_id, image in group.images.items():
            node = backend.network.nodes[node_id]
            for name, value in image['attrs'].items():
                if name == 'modules': continue
                try:restored=deepcopy(value)
                except TypeError:restored=value
                if name=='state' and isinstance(getattr(node,name,None),dict):
                    getattr(node,name).clear();getattr(node,name).update(restored)
                else:setattr(node, name, restored)
            # Keep state object identities: active component contexts still refer to them.
            for name, spec in image['attrs']['modules'].items():
                live = node.modules[name]
                live['state'].clear(); live['state'].update(deepcopy(spec['state']))
            node.tools.clear(); node.tools.update(image['tools'])
            node.tool_definitions = deepcopy(image['definitions'])
            node.agent_tool_definitions = deepcopy(image['agent_definitions'])
            node.tool_refusals = dict(image['refusals'])
            if image['inputs'] is not None:
                with node.inputs.lock:
                    node.inputs.sources = deepcopy(image['inputs'])
            if hasattr(backend, 'agents'):
                if image['binding'] is None: backend.agents.pop(node_id, None)
                else: backend.agents[node_id] = deepcopy(image['binding'])
            modules = getattr(backend, 'modules', None)
            if modules:
                for key in [key for key in modules._published if key[0] == node_id]:
                    modules._published.pop(key); backend.network.metadata_registry.unregister('module:' + repr(key))
                for key, value in image['published'].items():
                    modules._published[key] = deepcopy(value)
                    backend.network.metadata_registry.register('module:' + repr(key), lambda target, key=key: modules._metadata_fields(key, target))
            for path, content in image['files'].items():
                if content is None: path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_name(path.name + '.node-rollback.tmp')
                    temporary.write_bytes(content); temporary.replace(path)

    def overrides(self, committing=None):
        entries, images = {}, {}
        for group in set(self.exclusive.values()):
            if group is committing: continue
            entries.update(group.entries); images.update(group.images)
        return entries, images

    def routing(self, node_id):
        """Uncommitted edits do not change somebody else's routing view."""
        with self.condition:
            group = self.exclusive.get(node_id)
            if group and group is not self.current and node_id in group.images:
                attrs = group.images[node_id]['attrs']
                return tuple(attrs['interfaces']), attrs['divergence']
            node = self.backend.network.nodes[node_id]
            return tuple(node.interfaces), node.divergence

    def require_mutable(self, node_id):
        group = self.current
        if group and node_id not in group.nodes:
            raise PermissionError('Mutation requires this node in the current lock group')

    def lifecycle(self, node_id=None):
        if self.exclusive and (node_id is None or node_id in self.exclusive):
            raise RuntimeError('Node/module lifecycle changes are unavailable during a node transaction')


class NodeLockScope:
    def __init__(self, locks, nodes, validate, timeout, finish):
        self.locks, self.nodes, self.validate = locks, nodes, validate
        self.timeout, self.finish = timeout, finish
        self.group = None; self.token = None; self.owner_token = None; self.closed = False

    def __await__(self):return self.__aenter__().__await__()

    async def commit(self):
        if self.group is None:raise RuntimeError('Acquire the node lock before committing')
        return await self.__aexit__(None,None,None)

    async def rollback(self):
        if self.group is None:raise RuntimeError('Acquire the node lock before rolling back')
        return await self.__aexit__(RuntimeError,RuntimeError('Explicit node rollback'),None)

    async def __aenter__(self):
        if self.group is not None or self.closed: raise RuntimeError('Node lock scope cannot be reused')
        locks = self.locks; owner, self.owner_token = locks._identity()
        self.owner = owner
        try:
            with locks.condition:
                self.validate(); parent = locks.current
                if parent:
                    if not set(self.nodes) <= set(parent.nodes):
                        raise RuntimeError('Nested node locks may reenter, but cannot expand the locked group')
                    parent.depth += 1; self.group = parent
                    return self
            deadline = time.monotonic() + self.timeout
            while True:
                await locks._wait(lambda: locks._prepared() and locks._drained(self.nodes, owner), deadline,owner=owner,nodes=self.nodes,drain=True)
                with locks.condition:
                    if not locks._prepared() or not locks._drained(self.nodes, owner): continue
                    self.validate()
                    group = _Group(owner, self.nodes,executor=locks._executor())
                    for n in self.nodes: locks.exclusive[n] = group
                    try: locks._capture(group)
                    except BaseException:
                        for n in self.nodes: del locks.exclusive[n]
                        locks._notify(); raise
                    group.phase = 'capturing_contexts'; self.group = group
                    break
            try:
                contexts = await asyncio.wait_for(locks.backend.capture_node_contexts(group.nodes),self.timeout) if hasattr(locks.backend,'capture_node_contexts') else {}
                with locks.condition:
                    group.contexts=deepcopy(contexts)
                    for node,cursor in contexts.items():
                        group.images[node]['attrs']['context_cursor']=deepcopy(cursor)
                        group.entries[node]['context_cursor']=deepcopy(cursor)
                        group.records[node]['node']['context_cursor']=deepcopy(cursor)
                        locks.backend.network.nodes[node].context_cursor=deepcopy(cursor)
                    group.phase='active';locks._notify()
                # Publish the before-image (including the fresh log cursor)
                # durably before any transactional business code is admitted.
                await self._commit(before=True)
                self.token=_transaction.set(group)
                return self
            except BaseException:
                with locks.condition:
                    group.phase='closed'
                    for node in group.nodes:locks.exclusive.pop(node,None)
                    locks._notify()
                self.group=None;raise
        except BaseException:
            if self.owner_token is not None:
                owner.live = False; _owner.reset(self.owner_token)
            raise

    async def __aexit__(self, kind, error, traceback):
        if self.closed: return False
        if self.group is None:raise RuntimeError('Node lock was not acquired')
        locks, group = self.locks, self.group
        failure = error;restored=False
        try:
            if self.finish:
                try: await self.finish(error is not None)
                except BaseException as exc: failure = exc
            with locks.condition:
                if failure is not None: group.rollback_only = True
                group.depth -= 1
                if self.token is None: return False
                if group.depth:
                    group.rollback_only = True
                    raise RuntimeError('Nested lock scopes must finish before their parent')
            if group.rollback_only:
                with locks.condition:locks._restore(group)
                await self._restore_contexts()
                restored=True
            else:
                if hasattr(locks.backend,'capture_node_contexts'):
                    contexts=await locks.backend.capture_node_contexts(group.nodes)
                    with locks.condition:
                        for node,cursor in contexts.items():locks.backend.network.nodes[node].context_cursor=deepcopy(cursor)
                with locks.condition:
                    modules=getattr(locks.backend,'modules',None)
                    if modules:
                        for (node,_),module in modules.instances.items():
                            if node in group.nodes:module.definition.validate(module.state,module.definition.state_schema)
                await self._commit()
            if group.rollback_only and failure is None:raise RuntimeError('Nested node transaction was rolled back')
            if failure is not None and error is None: raise failure
        except BaseException:
            if self.token is not None and not restored:
                if group.rollback_only:
                    locks.backend.failed=True
                else:
                    group.rollback_only=True
                    try:
                        with locks.condition:locks._restore(group)
                        await self._restore_contexts()
                    except BaseException:locks.backend.failed=True
            raise
        finally:
            self.closed = True
            if self.token is not None:
                with locks.condition:
                    group.phase = 'closed'
                    for n in group.nodes: locks.exclusive.pop(n, None)
                    _transaction.reset(self.token); locks._notify()
            if self.owner_token is not None:
                self.owner.live = False; _owner.reset(self.owner_token)
        return False

    async def _restore_contexts(self):
        if self.group.contexts:
            try:
                await self.locks.backend.restore_node_contexts(self.group.contexts)
                await self._commit()
            except BaseException:
                self.locks.backend.failed=True
                raise

    async def _commit(self, *, before=False):
        if not hasattr(self.locks.backend,'commit_node_transaction'):return
        while True:
            await self.locks.wait_prepared()
            with self.locks.condition:
                if not self.locks._prepared():continue
                self.locks.backend.commit_node_transaction(None if before else self.group)
                return
