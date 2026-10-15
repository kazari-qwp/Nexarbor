from datanet.core.application import Component


class Plugin(Component):
    def install(self):
        self.discovered = {}
        self.on('agent/bound', lambda e: self.section(e['actor'], 'datanet:shared-agent-rules', self.r.resource(self.id, 'AGENTS.md')))
        self.on('tool/definition', self.definition)

    def definition(self, e):
        if e['name'] == 'network_structure':
            depth = self.r.state(e['actor'])['grant']['framework'][e['name']].get('max_depth', 100)
            e['spec']['parameters']['properties']['depth']['maximum'] = depth
            e['spec']['description'] = f'从所属节点查看连接摘要，默认使用最大depth，起点第0层，每个接口计1层；最大depth={depth}表示查看全部获准拓扑。只查看结构，不扩大数据或操作权限。'

    def invoke(self, actor, name, p):
        methods = dict(node_read='read', node_write='write', node_list='list_nodes', node_tools='list_tools', node_invoke='invoke_tool')
        if name == 'network_structure':
            options = self.r.state(actor)['grant']['framework'][name]
            maximum = options.get('max_depth', 100)
            return self.r.rpc(name, actor=actor, direction=p.get('direction', 'read'), depth=p.get('depth', maximum), max_depth=maximum, inspect_private=options.get('inspect_private', False))
        if name == 'node_invoke' and (p['target'], p.get('direction', 'read'), p['tool']) not in self.discovered.get(actor, set()):
            raise PermissionError('Discover the exposed node tool first')
        result = self.r.rpc(methods[name], actor=actor, **p)
        if name == 'node_list':
            for item in result.get('items', []):
                item['has_agent'] = item['node_id'] in self.r.states
        if name == 'node_tools':
            if not result.get('items'):
                return '该节点并未有向你开放的工具'
            discovered = self.discovered.setdefault(actor, set())
            for item in result['items']:
                discovered.add((p['target'], p.get('direction', 'read'), item['name']))
        return result
