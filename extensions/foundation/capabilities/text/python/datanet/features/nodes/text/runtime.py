from hashlib import sha256
from datanet.core.application import Component

QUERY_DESCRIPTION = '读取该查询文本，将当前正文加入上下文；需要时再次查询。'


class Plugin(Component):
    def install(self):
        self.targets = {}
        self.on('agent/bound', lambda e: self.sync(e['actor']))
        self.on('context/prepare', lambda e: self.sync(e['actor']))
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
        self.r.refresh(actor)

    def invoke(self, actor, name, p):
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
