"""Harness application routing and lifecycle over the reusable JSON-RPC transport."""
from threading import RLock
from datanet.communication.jsonrpc import JsonRpcTransport


class Transport(JsonRpcTransport):
    def __init__(self, backend, output=None):
        super().__init__(output=output, host_timeout=lambda method, params:
            max(600, params.get('timeout_ms', 180000) / 1000 + 30) if method == 'run' else 600)
        self.backend = backend
        self.application_lock = RLock()
        self.application = None
        backend.commit_observer = lambda commit_id: self.write(dict(notification='core/committed', commit_id=commit_id))

    def dispatch(self, method, p):
        from datanet.core.application import Application
        if method == 'application/catalog':
            return [dict(id=key, directory=str(self.backend.components.catalog[key]['implementation_directory']), harness=self.backend.components.catalog[key]['harness']) for key in self.backend.components.order if key in self.backend.components.enabled and self.backend.components.catalog[key].get('harness')]
        if method == 'application/start':
            with self.application_lock:
                if self.application is None:
                    self.application = Application(self.backend, self.host, p.get('config', {}))
            return {'ok': True}
        if not method.startswith('application/'):
            return self.backend.dispatch(method, p)
        app = self.application
        if app is None:
            raise RuntimeError('Application has not started')
        action = method.split('/', 1)[1]
        if action == 'component':
            # Trusted host extension surface; components own their operation tables.
            plugin = app.plugins.get(p['component'])
            if plugin is None or p['component'] not in app.enabled or not hasattr(plugin, 'host_request'):
                raise PermissionError('Component has no host operation interface')
            return plugin.host_request(p['operation'], p.get('params', {}))
        if action == 'root':
            return app.bind_session(p['session_id'])
        if action == 'invoke':
            return app.invoke(p['actor'], p['name'], p.get('arguments', {}), p.get('execution_id'))
        if action == 'event':
            return app.event(p['actor'], p['name'], p.get('payload', {}))
        if action == 'guard':
            payload = dict(actor=p['actor'], name=p['name'], arguments=p.get('arguments', {}), reason=None)
            for owner, function in app.listeners['tool/guard']:
                if owner in app.enabled:
                    function(payload)
            return payload['reason']
        if action == 'inputs':
            return app.update_inputs(p['actor'],p['source'],**p.get('patch',{}))
        if action == 'tail':
            payload = dict(actor=p['actor'], texts=app.input_tail(p['actor']))
            for owner, function in app.listeners['context/tail']:
                if owner in app.enabled:
                    function(payload)
            return payload['texts']
        if action == 'view':
            return app.view(p['actor'])
        if action == 'disable':
            return app.disable(p['component'])
        raise ValueError('Unknown application operation: ' + action)

    def close(self):
        if self.application:
            for plugin in self.application.plugins.values():
                if hasattr(plugin, 'close'): plugin.close()
        self.backend.close()
