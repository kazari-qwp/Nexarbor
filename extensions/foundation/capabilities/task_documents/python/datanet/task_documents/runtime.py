"""Task inputs and per-worker deliveries over ordinary persistent text nodes."""
import hashlib
import json
from threading import RLock
from uuid import uuid4

from datanet.core.application import Component, checked
from datanet.core.interface import Interface
from datanet.core.component_registry import codecs


class Plugin(Component):
    def install(self):
        self.lock = RLock()

    @property
    def tasks(self):
        return self.r.backend.extension_state.setdefault('task_documents', {})

    def task(self, actor, task_id=None):
        if task_id is None:
            task_id = self.r.backend.agents.get(actor, {}).get('document_task')
        task = self.tasks.get(task_id)
        if task is None or actor not in task['members']:
            raise PermissionError('Task is not assigned to this Agent')
        return task

    def node(self, task, suffix, title, content):
        id = task['id'] + '/' + suffix
        node = codecs()['text_file'].node_class(id, title, 'text', self.r.directory / 'tasks' / task['id'].split('/')[-1] / (suffix + '.md'))
        node.management_parent_id = task['owner']
        checked(node.write('content', content))
        self.r.backend.network.add_node(node)
        return id

    def begin(self, actor, content, *, mode='agent', references=None):
        with self.lock:
            if mode not in ('agent', 'read', 'write'):
                raise ValueError('Task mode must be agent, read or write')
            if actor not in self.r.backend.agents:
                raise PermissionError('Task owner must be a bound Agent')
            task = dict(id='task/' + uuid4().hex, owner=actor, mode=mode, members={}, documents={})
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            task['input'] = self.node(task, 'input', '原始任务', text)
            task['references'] = references or []
            self.tasks[task['id']] = task
            self.attach(task, actor)
            self.r.rpc('save')
            return self.reference(actor, task)

    def attach(self, task, actor):
        if actor not in task['members']:
            result = self.node(task, 'result-' + actor.encode().hex(), '交付文档：' + actor, '')
            task['members'][actor] = result
            task['documents'][result] = dict(author=actor, revision=0, sources=[], receipts=[])
        self.r.backend.agents[actor]['document_task'] = task['id']
        self.connect(task)

    def connect(self, task):
        network = self.r.backend.network
        for actor, result in task['members'].items():
            node = network.nodes[actor]
            for id in [task['input'], *task['documents']]:
                node.connect(id,channels=('access.read',),visibility='private')
            node.connect(result,channels=('access.write',),visibility='private')

    def reference(self, actor, task):
        return dict(task_id=task['id'], mode=task['mode'], input_id=task['input'],
                    result_id=task['members'][actor], references=task['references'])

    def tool_task_document_read(self, actor, args):
        with self.lock:
            task = self.task(actor, args.get('task_id'))
            id = args.get('node_id', task['input'])
            if id not in [task['input'], *task['documents']]:
                raise PermissionError('Document is outside this task')
            if not any(n.node_id == id for n, _ in self.r.backend.network.walk(actor, strength=self.r.state(actor)['strength'])):
                raise PermissionError('Document is outside read access')
            node = self.r.backend.network.nodes[id]
            content = node.file_path.read_text(encoding='utf-8')
            return dict(**self.reference(actor, task), node_id=id, content=content,
                        **task['documents'].get(id, dict(immutable=True)),
                        sha256=hashlib.sha256(content.encode()).hexdigest(),
                        deliveries=[dict(node_id=id, author=meta['author'], revision=meta['revision']) for id, meta in task['documents'].items()])

    def tool_task_document_write(self, actor, args):
        with self.lock:
            task = self.task(actor, args.get('task_id'))
            id = task['members'][actor]
            meta = task['documents'][id]
            if args.get('expected_revision', meta['revision']) != meta['revision']:
                raise ValueError('Delivery revision changed; read it before retrying')
            sources = args.get('sources', [])
            readable = {n.node_id for n, _ in self.r.backend.network.walk(actor, strength=self.r.state(actor)['strength'])}
            for source in sources:
                if source.get('node_id') not in readable:
                    raise PermissionError('Evidence node is outside read access')
                self.r.emit('document/validate-source', actor=actor, source=source)
            receipts = args.get('receipts', [])
            self.r.emit('document/validate-receipts', actor=actor, receipts=receipts, task=task)
            checked(self.r.backend.network.write(actor, id, 'content', args['content'], strength=self.r.state(actor)['strength']))
            meta.update(revision=meta['revision'] + 1, sources=sources, receipts=receipts)
            self.r.rpc('save')
            return dict(node_id=id, revision=meta['revision'], written=True)
