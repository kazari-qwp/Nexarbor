from datanet.components.nodes.text_file_node.text_file_node import TextFileNode
TEXT_PRESETS = {mode + '_text': {'type': 'text_file', 'name': label, 'data_kind': 'text', 'description': description, 'parameters': {'file_path': 'document.md', 'delivery': mode}, 'toolboxes': ['local_data'], 'expose': ['get_schema', 'write'] + (['read'] if mode == 'query' else [])} for mode, label, description in [('resident', '常驻文本', '正文随读取连接自动放入Agent请求尾部。'), ('query', '查询文本', '向读取者提供绑定本节点的查询工具，按需加载正文。')]}

def label(node):
    return '[' + node.name + '：' + node.node_id + ']' + ('(' + node.description + ')' if node.description else '')

def bindings(backend, p, direction='read'):
    owner = backend.network.nodes[p['actor']]
    targets = {edge.target_node_id for edge in getattr(owner, direction + '_interfaces') if edge.allows(origin_node_id=owner.node_id, source_node_id=owner.node_id, strength=p.get('strength', 0))}
    return [backend.network.nodes[x] for x in sorted(targets) if type(backend.network.nodes[x]) is TextFileNode and (backend.network.nodes[x].delivery in ('resident', 'query'))]

def dispatch(backend, method, p):
    if method == 'text_bindings':
        return {'read': [{'node_id': n.node_id, 'name': n.name, 'description': n.description, 'delivery': n.delivery, 'label': label(n)} for n in bindings(backend, p)], 'write': [{'node_id': n.node_id, 'name': n.name} for n in bindings(backend, p, 'write') if n.delivery == 'resident']}
    if method == 'resident_texts':
        result = []
        for node in bindings(backend, p):
            if node.delivery != 'resident':
                continue
            content = node._read_key('content')
            if content.status == 'not_found':
                text = ''
            elif content.status == 'ok':
                text = content.items[0]['content']
            else:
                raise OSError('; '.join(content.errors))
            result.append({'node_id': node.node_id, 'text': label(node) + '\n' + text})
        return {'texts': result}
    if method in ('query_text', 'write_resident_text'):
        direction = 'read' if method == 'query_text' else 'write'
        nodes = bindings(backend, p, direction)
        target = p.get('target')
        if target is None and method == 'write_resident_text':
            nodes = [n for n in nodes if n.delivery == 'resident']
            if len(nodes) == 1:
                target = nodes[0].node_id
        node = next((n for n in nodes if n.node_id == target), None)
        expected = 'query' if method == 'query_text' else 'resident'
        if node is None or node.delivery != expected:
            raise PermissionError('目标不在该节点的' + ('查询文本读取' if direction == 'read' else '常驻文本写入') + '连接中')
        if method == 'write_resident_text':
            return backend.network.write(p['actor'], node.node_id, 'content', p['content'], strength=p.get('strength', 0), mode=p.get('mode', 'upsert'))
        result = node.read({'method': 'key', 'key': 'content'})
        if result.status != 'ok':
            return result
        return {'node_id': node.node_id, 'text': label(node) + '\n' + result.items[0]['content']}
    raise ValueError(method)

def register(services):
    services.node_presets.update(TEXT_PRESETS)
    for method in ('text_bindings', 'resident_texts', 'query_text', 'write_resident_text'):
        services.rpc(method, lambda backend, p, method=method: dispatch(backend, method, p), mutation=method == 'write_resident_text')
