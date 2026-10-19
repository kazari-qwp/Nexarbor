"""Concurrent newline JSON-RPC with reverse host calls, independent of graph state."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from threading import Event, Lock
import json
import sys
import uuid


class JsonRpcTransport:
    def __init__(self, dispatch=None, output=None, *, workers=64, host_timeout=None):
        self.handler, self.output = dispatch, output or sys.stdout
        self.pending, self.output_lock, self.pending_lock = {}, Lock(), Lock()
        self.workers = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='datanet-rpc')
        self.closed = False
        self.host_timeout = host_timeout or (lambda method, params: 600)

    def dispatch(self, method, params):
        if self.handler is None: raise NotImplementedError('No RPC handler registered')
        return self.handler(method, params)

    def close(self):
        """Host lifecycle hook, called after admitted requests have drained."""

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
            if self.closed: raise RuntimeError('Host connection closed')
            self.pending[token] = record
        self.write(dict(host_id=token, method=method, params=params))
        try:
            timeout = self.host_timeout(method, params)
            if not event.wait(timeout):
                raise TimeoutError('Host port timeout: ' + method)
            response = record['response']
            if response.get('error'):
                raise RuntimeError(response['error'])
            return response.get('result')
        finally:
            with self.pending_lock:
                self.pending.pop(token, None)

    def answer(self, request):
        try:
            self.write(dict(id=request['id'], result=self.dispatch(request['method'], request.get('params', {}))))
        except Exception as error:
            self.write(dict(id=request.get('id'), error=str(error) or type(error).__name__))

    def run(self, stream):
        try:
            for line in stream:
                try:
                    request = json.loads(line)
                    if not isinstance(request, dict): raise ValueError('RPC message must be an object')
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
                self.closed = True
                for record in self.pending.values():
                    record['response'] = {'error': 'Host connection closed'}
                    record['event'].set()
            self.workers.shutdown(wait=True)
            self.close()
