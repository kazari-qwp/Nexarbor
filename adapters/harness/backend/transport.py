"""Duplex JSON-RPC transport. Reverse calls never hold the graph transaction lock."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from threading import Event, Lock, RLock
import json
import sys
import uuid


class Transport:
    def __init__(self, backend, output=None):
        self.backend, self.output = backend, output or sys.stdout
        self.pending, self.output_lock, self.pending_lock = {}, Lock(), Lock()
        self.application_lock = RLock()
        self.workers = ThreadPoolExecutor(max_workers=64, thread_name_prefix='datanet-rpc')
        self.application = None

    def write(self, value):
        def encode(item):
            if is_dataclass(item):
                return asdict(item)
            raise TypeError(type(item).__name__)
        line = json.dumps(value, default=encode, ensure_ascii=False, allow_nan=False)
        with self.output_lock:
            self.output.write(line + '\n')
            self.output.flush()

    def host(self, method, params):
        token, event = uuid.uuid4().hex, Event()
        record = {'event': event}
        with self.pending_lock:
            self.pending[token] = record
        self.write(dict(host_id=token, method=method, params=params))
        try:
            timeout = max(600, params.get('timeout_ms', 180000) / 1000 + 30) if method == 'run' else 600
            if not event.wait(timeout):
                raise TimeoutError('Harness port timeout: ' + method)
            response = record['response']
            if response.get('error'):
                raise RuntimeError(response['error'])
            return response.get('result')
        finally:
            with self.pending_lock:
                self.pending.pop(token, None)

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
        if action == 'tail':
            payload = dict(actor=p['actor'], texts=[])
            for owner, function in app.listeners['context/tail']:
                if owner in app.enabled:
                    function(payload)
            return payload['texts']
        if action == 'view':
            return app.view(p['actor'])
        if action == 'disable':
            return app.disable(p['component'])
        raise ValueError('Unknown application operation: ' + action)

    def answer(self, request):
        try:
            self.write(dict(id=request['id'], result=self.dispatch(request['method'], request.get('params', {}))))
        except Exception as error:
            self.write(dict(id=request.get('id'), error=str(error)))

    def run(self, stream):
        try:
            for line in stream:
                try:
                    request = json.loads(line)
                except Exception as error:
                    self.write(dict(id=None, error=str(error)))
                    continue
                if 'host_id' in request:
                    with self.pending_lock:
                        record = self.pending.get(request['host_id'])
                        if record:
                            record['response'] = request
                            record['event'].set()
                else:
                    self.workers.submit(self.answer, request)
        finally:
            with self.pending_lock:
                for record in self.pending.values():
                    record['response'] = {'error': 'Harness connection closed'}
                    record['event'].set()
            self.workers.shutdown(wait=True)
            if self.application:
                for plugin in self.application.plugins.values():
                    if hasattr(plugin, 'close'):
                        plugin.close()
            self.backend.close()
