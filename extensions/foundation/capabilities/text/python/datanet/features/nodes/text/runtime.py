from hashlib import sha256
from datanet.core.application import Component

QUERY_DESCRIPTION = '读取该查询文本，将当前正文加入上下文；需要时再次查询。'
WRITE_DESCRIPTION = '写入有写入连接的常驻文本。target只能选择这些常驻文本节点；只有一个目标时可省略。'


class Plugin(Component):
    def install(self):
        self.targets = {}
        self.on('agent/bound', lambda e: self.sync(e['actor']))
        self.on('context/prepare', lambda e: self.sync(e['actor']))
        self.on('context/tail', self.tail)
        self.on('graph/changed', lambda e: [self.sync(actor) for actor in self.r.states])
        self.on('discussion/member-start', self.project)

    def params(self, actor):
        return dict(actor=actor, strength=self.r.state(actor)['strength'])

    def sync(self, actor):
        bindings = self.r.rpc('text_bindings', **self.params(actor))
        dynamic = self.r.state(actor)['dynamic']
        for name in list(dynamic):
            if dynamic[name]['owner'] == self.id:
                del dynamic[name]
        self.targets[actor] = {}
        for node in bindings['read']:
            if node['delivery'] != 'query':
                continue
            name = 'query_text_' + sha256(node['node_id'].encode()).hexdigest()[:16]
            dynamic[name] = dict(owner=self.id, name=name, description=node['label'] + '\n' + QUERY_DESCRIPTION, parameters=dict(type='object', properties={}, additionalProperties=False))
            self.targets[actor][name] = node['node_id']
        if bindings['write']:
            dynamic['write_resident_text'] = dict(owner=self.id, name='write_resident_text', description=WRITE_DESCRIPTION, parameters=dict(type='object', properties={'target': {'type': 'string', 'description': '有写入连接的常驻文本节点ID。'}, 'content': {'type': 'string'}, 'mode': {'type': 'string', 'enum': ['upsert', 'append'], 'default': 'upsert'}}, required=['content'], additionalProperties=False))
        self.r.refresh(actor)

    def tail(self, e):
        e['texts'].extend(node['text'] for node in self.r.rpc('resident_texts', **self.params(e['actor']))['texts'])

    def invoke(self, actor, name, p):
        if name == 'write_resident_text':
            return self.r.rpc(name, **self.params(actor), **p)
        target = self.targets[actor][name]
        result = self.r.rpc('query_text', **self.params(actor), target=target)
        return dict(node_id=target, instructions_added=self.r.load(actor, 'query-text:' + target, result['text']))

    def project(self, e):
        actor = e['actor']
        if all(self.r.host('document-present', actor=actor, document='query-text:' + target) for target in e['project_ids']):
            return
        result = self.r.rpc('load_project', **self.params(actor), group_id=e['group_id'])
        for node in result['items']:
            label = '[' + node['name'] + '：' + node['node_id'] + ']' + ('(' + node['description'] + ')' if node.get('description') else '')
            self.r.load(actor, 'query-text:' + node['node_id'], label + '\n' + node['content'])
