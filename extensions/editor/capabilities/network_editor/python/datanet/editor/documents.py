"""Portable editor documents. Reuse component resources and native graph codecs."""
from copy import deepcopy
from pathlib import Path, PurePosixPath
import json
import re


def relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('文档路径必须是工作区内的相对路径')
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ('.', '..') for p in path.parts):
        raise ValueError('文档路径不能越出工作区')
    return value


def portable(snapshot):
    """Export graph/files, never host session identities or projection caches."""
    network = deepcopy(snapshot['network'])
    for node in network['nodes']:
        for name in ('file_path', 'content_path', 'metadata_path','db_path','directory','storage_path'):
            if isinstance(node.get('parameters', {}).get(name), str):
                node['parameters'][name] = node['parameters'][name].replace('\\', '/')
    files = {}
    for key, value in snapshot.get('files', {}).items():
        key = key.replace('\\', '/')
        if key in files: raise ValueError('资源路径规范化后重复：' + key)
        files[key] = deepcopy(value)
    return dict(version=1, network=network, agents={}, files=files, tools={}, tool_names={})


def resource(catalog, owner, file):
    root = catalog[owner]['directory']
    target = (root / relative(file)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('组件资源越出目录')
    return target.read_text(encoding='utf-8')


def preset(catalog, key):
    manifest = catalog[key]
    document = portable(json.loads(resource(catalog, key, manifest['initialNetwork'])))
    for path, src in manifest.get('initialFiles', {}).items():
        document['files'][relative(path)] = resource(catalog, src['component'], src['file']) if isinstance(src, dict) else src
    # Existing operator recipes store the pulse payload on their own module.
    # Materialize that authored configuration so direct pulse control is equivalent.
    by = {n['node_id']: n for n in document['network']['nodes']}
    for node in by.values():
        for spec in node['modules'].values():
            config = spec['config']
            if all(k in config for k in ('pulse', 'task')) and config['pulse'] in by:
                target = by[config['pulse']]
                if target['type'] == 'pulse' and target['parameters'].get('content') is None:
                    target['parameters']['content'] = dict(task=config['task'], timeout_ms=90000)
    return document


def safe_document(document, catalog, enabled):
    """Editor scope: the four core node types and portable text resources only."""
    if not isinstance(document, dict) or document.get('version') != 1:
        raise ValueError('不是有效的编辑器网络文档')
    if len(json.dumps(document, ensure_ascii=False)) > 8_000_000:
        raise ValueError('文档超过8MB')
    doc = portable(document)
    if doc['network'].get('signals'):
        # Runtime histories are observations, not authored signal programs.
        doc['network']['signals'] = {}
    for path, content in doc['files'].items():
        relative(path)
        from datanet.core.resource_data import decode_data
        decode_data(content)
    def sources(value):
        if isinstance(value, list):
            for item in value: sources(item)
        if not isinstance(value, dict): return
        if value.get('type') == 'file' and 'path' in value:
            raise ValueError('编辑器使用文档节点或组件资源；不接受任意磁盘文件来源')
        if 'document_roots' in value and value['document_roots']:
            raise ValueError('请将文档导入资源面板，不开放外部目录')
        if 'component' in value and 'file' in value:
            if value['component'] not in enabled: raise ValueError('组件未启用：' + value['component'])
            resource(catalog, value['component'], value['file'])
        for item in value.values(): sources(item)
    ids = set()
    for node in doc['network']['nodes']:
        key = node['node_id']
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,180}', key) or '..' in key:
            raise ValueError('节点编号仅使用字母、数字、下划线、短横线和路径分隔符')
        if key in ids: raise ValueError('节点编号重复：' + key)
        ids.add(key)
        from datanet.core.component_registry import active_codecs
        if node['type'] not in active_codecs():
            raise ValueError('此编辑器暂不支持节点类型：' + node['type'])
        if node.get('agent') is not None or node.get('execution') is not None:
            raise ValueError('执行器绑定由宿主建立，不从导入文件载入')
        for name in ('file_path', 'content_path', 'metadata_path','db_path','directory','storage_path'):
            if node['parameters'].get(name): relative(node['parameters'][name])
        sources(node['modules'])
    if 'root' not in ids: raise ValueError('网络必须保留根 Agent 节点')
    return doc


def replace(value, replacements):
    if isinstance(value, str):
        for old, new in sorted(replacements.items(), key=lambda pair: -len(pair[0])):
            value = value.replace(old, new)
        return value
    if isinstance(value, list): return [replace(v, replacements) for v in value]
    if isinstance(value, dict): return {k: replace(v, replacements) for k, v in value.items()}
    return value


def refresh_map(document):
    """NPC recipe document generator; graph connections remain the authority."""
    by = {n['node_id']: n for n in document['network']['nodes']}
    target = by.get('world/map')
    if not target: return document
    places = {k: n for k, n in by.items() if 'world.address' in n['modules']}
    clean = lambda value: value.replace('|', '／').replace('\n', ' ')
    lines = ['# 小镇地图', '', '| 地点 | 可直接前往 |', '|---|---|']
    for key, node in places.items():
        neighbors = list(dict.fromkeys(e['target_node_id'] for e in node['connections']['interfaces'] if e['target_node_id'] in places))
        lines.append('| ' + clean(node['name']) + ' | ' + ('、'.join(clean(places[k]['name']) for k in neighbors) or '无') + ' |')
    document['files'][target['parameters']['file_path']] = '\n'.join(lines) + '\n'
    return document


def template(catalog, document, kind, options):
    """Recipes are configuration transforms; existing modules implement behavior."""
    full = preset(catalog, 'network_presets/small_town')
    doc = deepcopy(document)
    nodes = doc['network']['nodes']
    by = {n['node_id']: n for n in nodes}
    original = {n['node_id']: n for n in full['network']['nodes']}
    if kind == 'empty':
        root = deepcopy(original['root']); root['modules'] = {}
        return dict(version=1, network=dict(version=6, nodes=[root], signals={}, delegations=[]), agents={}, files={'root-memory.md': ''}, tools={}, tool_names={})
    if kind == 'infrastructure':
        for key, node in original.items():
            if key == 'root' or key.startswith(('world/place/', 'world/service/', 'world/npc/')): continue
            if key in by: continue
            node = deepcopy(node)
            for direction in node['connections']:
                node['connections'][direction] = [e for e in node['connections'][direction] if not e['target_node_id'].startswith('world/npc/')]
            nodes.append(node)
        # The operator is optional; the editor starts the configured pulse directly.
        doc['files'].update(full['files'])
        return refresh_map(doc)
    if kind in ('place', 'resident') and 'world/time' not in by:
        raise ValueError('先添加“时间与共享资料”，再添加场所和居民')
    slug = options.get('id', '')
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,50}', slug): raise ValueError('编号请使用小写字母开头的英文、数字或短横线')
    if kind == 'place':
        source = options.get('kind', 'forest')
        old = 'world/place/' + source; target = 'world/place/' + slug
        service = 'world/service/' + slug
        if old not in original: raise ValueError('未知场所模板')
        if target in by or service in by: raise ValueError('场所编号已存在')
        replacements = {old: target, 'world/service/' + source: service}
        for key in (old, 'world/service/' + source):
            node = replace(original[key], replacements)
            node['name'] = options.get('name', slug) + ('服务' if key.startswith('world/service') else '')
            node['connections'] = {direction: [] for direction in node['connections']}
            node['modules'].pop('probability.events', None)
            if 'world.household' in node['modules']: node['modules']['world.household']['state']['residents'] = []
            if 'world.birth' in node['modules']:
                node['modules']['world.birth']['config']['families'] = [n['node_id'] for n in nodes if 'world.family' in n['modules']]
            nodes.append(node)
        link(doc,target,service)
        return refresh_map(doc)
    if kind == 'resident':
        actor = 'world/npc/' + slug
        if actor in by: raise ValueError('居民编号已存在')
        place = options.get('place')
        if place not in by or 'world.address' not in by[place]['modules']: raise ValueError('请选择居民初始场所')
        role = options.get('role', 'resident')
        sample = {'miner': 'miner', 'woodcutter': 'woodcutter', 'smith': 'smith', 'wanderer': 'wanderer'}.get(role, 'lin')
        old = 'world/npc/' + sample
        replacements = {old: actor, 'world/memories/' + sample + '.md': 'world/memories/' + slug + '.md'}
        resident = replace(original[old], replacements)
        context = replace(original[old + '/context'], replacements)
        resident['name'] = options.get('name', slug)
        context['name'] = resident['name'] + '的上下文'
        resident['connections'] = dict(interfaces=[])
        state = resident['modules']['world.resident']['state']
        state.update(id=slug, name=resident['name'], place=place, role=role, gender=options.get('gender', 'unspecified'), coins=options.get('coins', 10))
        for field in ('spouse',): state[field] = None
        for field in ('children', 'inbox'): state[field] = []
        state.pop('can_gestate', None)
        resident['modules']['input.opening']['config']['text'] = options.get('motivation', '')
        resident['modules']['world.knowledge']['config']['context'] = actor + '/context'
        personality = actor + '/personality'
        text_node = deepcopy(original['world/common'])
        text_node.update(node_id=personality, name=resident['name'] + '的人格')
        text_node['parameters']['file_path'] = 'world/personalities/' + slug + '.md'
        doc['files'][text_node['parameters']['file_path']] = options.get('personality', '')
        context['connections']['interfaces'] = [e for e in context['connections']['interfaces'] if e['target_node_id'] in by]
        for src in context['modules']['context.sources']['config']['sources']:
            if src['id'] == 'personality': src['source'] = dict(type='node', target=personality)
        nodes.extend([resident, context, text_node])
        link(doc, actor, actor + '/context', channels=('access.read',),visibility='private')
        link(doc, actor + '/context', personality, channels=('access.read',),visibility='private')
        link(doc, actor, place, reciprocal=True, attributes={'world_presence': True})
        link(doc, 'world/time', actor, channels=['world.tick'])
        link(doc, actor, 'world/savepoint', channels=['world.tick'])
        return doc
    if kind in ('node', 'agent', 'text_file', 'pulse'):
        key = options.get('id')
        if key in by: raise ValueError('节点编号已存在')
        sample = {'node': 'world/savepoint', 'agent': 'root', 'text_file': 'world/common', 'pulse': 'world/pulse'}[kind]
        node = deepcopy(original[sample]); node.update(node_id=key, name=options.get('name', key), modules={})
        node['connections'] = dict(interfaces=[])
        if kind in ('text_file', 'agent'):
            node['parameters'] = dict(file_path='editor/documents/' + key + '.md')
            if kind == 'agent': node['parameters']['creation_options'] = {}
            doc['files'][node['parameters']['file_path']] = ''
        nodes.append(node)
        return doc
    raise ValueError('未知模板')


def link(doc,source,target,*,reciprocal=False,channels=('access.read','access.write'),visibility='public',threshold=1,multiplier=1,attributes=None):
    by={n['node_id']:n for n in doc['network']['nodes']}
    for a,b in [(source,target)]+([(target,source)] if reciprocal else []):
        entry=dict(target_node_id=b,metadata=dict(visibility=visibility,threshold=threshold,multiplier=multiplier,channels=list(channels),attributes=attributes or {}))
        edges=by[a]['connections']['interfaces']
        if entry not in edges:edges.append(entry)
    return doc
