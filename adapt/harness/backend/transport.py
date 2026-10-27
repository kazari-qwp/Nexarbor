"""真实 Harness 运行、回调及检查点 RPC；应用路由在应用迁移时登记。"""

from adapt.communication.jsonrpc import JsonRpcTransport
from adapt.harness.executor import NativeExecutor
from app.persistence.recovery import acknowledge_executors, required_contexts, restore_bundle
from app.runtime.async_runtime import AsyncRuntime


class Transport(JsonRpcTransport):
    def __init__(self, backend, output=None):
        super().__init__(output=output, host_timeout=lambda method, params:
                         max(86460, params.get('timeout_seconds', 86400) + 60))
        self.backend = backend
        self.runtime = AsyncRuntime()
        self.executor = NativeExecutor(backend.network, self, bindings=backend.bindings,
                                       states=backend.agents, locks=backend.node_locks)
        backend.context_port = self.executor
        backend.agent_executor = self.executor.run
        backend.commit_observer = lambda commit_id: self.write(dict(notification='core/committed', commit_id=commit_id))
        for node in backend.network:
            if node.node_type == 'agent':
                backend.bindings.setdefault(node.info.node_id, {'executor': 'harness'})
                self.executor.attach(node.info.node_id, self.runtime)
        self.routes = {}

    def dispatch(self, method, p):
        backend = self.backend
        if method.startswith('executor_'):
            if required_contexts(backend.store):
                raise RuntimeError('Executor contexts must be restored to their saved positions before mounting Agents')
            with backend.node_locks.import_owner(p.get('node_access_ticket'), p.get('actor')):
                return self._executor(method.removeprefix('executor_'), p)
        if method == 'save':return backend.save(full=p.get('full', False))
        if method == 'state':return backend.snapshot()
        if method == 'persistence_info':return backend.persistence_info()
        if method == 'persistence_points':return backend.store.points()
        if method == 'persistence_checkpoint':return backend.checkpoint(**p)
        if method == 'persistence_mark':return backend.mark(**p)
        if method == 'persistence_latest_point':
            row = backend.store.db.execute('SELECT id FROM recovery_points ORDER BY rowid DESC LIMIT 1').fetchone()
            return backend.store.point(row[0]) if row else None
        if method == 'persistence_export':return backend.store.bundle(p['point_id'])
        if method == 'persistence_restore':
            return restore_bundle(backend.store.bundle(p['point_id']), p['directory'],
                                  sessions=p.get('sessions'), saver=backend.saver)
        if method == 'persistence_executor_restored':return acknowledge_executors(backend, p['sessions'])
        if method in self.routes:return self.routes[method](p)
        raise ValueError('Unknown runtime operation: ' + method)

    def _executor(self, action, p):
        if action in ('prepare', 'invoke'):
            return self.backend.perform('executor_' + action,
                lambda: self.runtime.run(getattr(self.executor, action)(p), timeout=86460))
        if action in ('ack', 'bind', 'prune'):
            return self.backend.perform('executor_' + action, lambda: getattr(self.executor, action)(p))
        if action == 'run':
            result = self.runtime.run(self.executor.run(p['actor'], p.get('text', '')), timeout=86460)
            self.backend.save()
            return result
        if action == 'read':
            with self.backend.node_locks.access_sync([p['actor']]):
                node, binding = self.executor.binding(p['actor'])
                state = self.backend.agents.get(p['actor'], {})
                with self.backend.node_locks.export_owner(p['actor']) as ticket:
                    return self.host('agent-read', dict(actor=p['actor'], name=node.info.name,
                        session_id=state.get('session_id'), context_cursor=state.get('context_cursor'),
                        model=binding.get('model'), model_signature=state.get('model_signature'), node_access_ticket=ticket))
        raise ValueError('Unknown executor operation: ' + action)

    def close(self):
        try:self.runtime.close()
        finally:self.backend.close()
