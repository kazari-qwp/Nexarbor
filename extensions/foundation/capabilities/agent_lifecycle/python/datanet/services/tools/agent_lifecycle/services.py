"""Disk-backed inactive graph fragments and root-scoped reusable employees."""
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import json
import base64
from datanet.core.serialization import save_network, _build
from datanet.core.component_registry import resource_paths, codec_for_node
from datanet.core.management import resolve_managed
from datanet.core.interface import Interface


def initialize(b):
    b.lifecycle = dict(archived={}, pool={}, confirmations={}, deferred=[], offline_groups={}, sleeping=False, fragments={})


def archive_entries(b):
    return [json.loads((b.directory / path).read_text(encoding='utf-8')) for id, path in b.lifecycle['archived'].items() if id not in b.network.nodes]


def configure(b):
    b.network.archived_entries = lambda: archive_entries(b)
    b.network.archived_ids = set(b.lifecycle['archived'])


def document(b):
    configure(b)
    path = b.directory / 'lifecycle-graph.tmp.json'
    save_network(b.network, path)
    return json.loads(path.read_text(encoding='utf-8'))


def records(b):
    with b._transaction_lock:
        return {n['node_id']: n for n in document(b)['nodes']}


def reachable(rows, origin='root'):
    seen, queue = set(), [origin]
    while queue:
        current = queue.pop()
        if current in seen or current not in rows:
            continue
        seen.add(current)
        for links in rows[current]['connections'].values():
            queue.extend(edge['target_node_id'] for edge in links)
    return seen


def graph_hash(rows):
    return sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write_record(b, row):
    relative = 'lifecycle/nodes/' + row['node_id'].encode().hex() + '.json'
    path = b.directory / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(row, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)
    b.lifecycle['archived'][row['node_id']] = relative


def store_groups(b, ids):
    for key, group in list(getattr(b, 'groups', {}).items()):
        if group['board'].node_id in ids:
            b.lifecycle['offline_groups'][key] = {k: v for k, v in group.items() if k != 'board'} | {'board_id': group['board'].node_id}
            del b.groups[key]


def park(b, p):
    ids = set(p['ids']) - {'root'}
    rows = records(b)
    if not p.get('sleeping'):
        ids -= reachable(rows)
    store_groups(b, ids)
    for target in ids:
        if target in b.network.nodes:
            write_record(b, rows[target])
            b.network.nodes.pop(target)
    configure(b)
    b.lifecycle['sleeping'] = p.get('sleeping', False)
    return {'unloaded': sorted(ids)}


def wake(b, p):
    rows = records(b)
    ids = reachable(rows) if p.get('target') is None else reachable(rows, p['target'])
    # Waking a contact does not silently reconnect a detached fragment to root.
    built = _build({'version':6,'signals':{},'nodes': list(rows.values()), 'delegations': []}, b.directory)
    for target in ids & b.lifecycle['archived'].keys():
        b.network.add_node(built.nodes[target])
        b.lifecycle['archived'].pop(target)
    configure(b)
    for key, value in list(b.lifecycle['offline_groups'].items()):
        if value['board_id'] in b.network.nodes:
            from datanet.services.network_presets.discussion_group.services import restore
            restore(b, {'groups': {key: value}})
            b.lifecycle['offline_groups'].pop(key)
    for node in list(b.network.nodes.values()):
        if hasattr(node, 'bind_network'):
            node.bind_network(b.network)
    b.lifecycle['sleeping'] = False
    return {'loaded': sorted(ids), 'reachable': sorted(reachable(rows))}


def remove_link(b, actor, args, options):
    node = resolve_managed(b.network, actor, args.get('node_id'), options.get('scope', 'self'))
    changes=[]
    links=node.interfaces;index=args.get('interface_index')
    candidates=[i for i,link in enumerate(links) if link.target_node_id==args['target_node_id'] and (index is None or i==index)]
    if len(candidates)!=1:raise ValueError('Interface absent or ambiguous; query indices')
    changes.append(('interfaces',candidates[0],asdict(links[candidates[0]])))
    return node, changes


def interfaces(b, p):
    actor, args, options = p['actor'], p['arguments'], p['options']
    if 'remove' not in options.get('actions', ['list', 'add', 'update', 'remove']):
        raise PermissionError('Removing interfaces is not granted')
    rows = records(b)
    token = args.get('confirmation_id')
    if token:
        pending = b.lifecycle['confirmations'].get(token)
        if not pending or pending['actor'] != actor:
            raise PermissionError('Confirmation is absent or belongs to another Agent')
        choice = args.get('choice')
        if choice not in (1, 2, 3):
            raise ValueError('Choose 1, 2 or 3')
        if choice == 1:
            b.lifecycle['confirmations'].pop(token)
            return {'status': 'ok', 'cancelled': True}
        if pending['revision'] != graph_hash(rows):
            b.lifecycle['confirmations'].pop(token)
            return {'status': 'ok', 'stale': True, 'message': '拓扑已变化，请重新提交拆除链接。'}
        args = pending['arguments']
        b.lifecycle['confirmations'].pop(token)
    else:
        choice = None
    node, changes = remove_link(b, actor, args, options)
    simulated = deepcopy(rows)
    for label, index, edge in changes:
        simulated[node.node_id]['connections'][label].pop(index)
    detached = sorted(reachable(rows) - reachable(simulated))
    if detached and choice is None:
        token = str(uuid4())
        b.lifecycle['confirmations'][token] = dict(actor=actor, arguments=deepcopy(args), revision=graph_hash(rows))
        return {'status': 'ok', 'confirmation_id': token, 'awaiting_confirmation': True, 'entry_node_id': args['target_node_id'], 'node_count': len(detached), 'agent_count': sum(id in b.agents for id in detached), 'message': '拆除链接将导致一部分节点和网络与根节点断开连接。', 'choices': {'1': '取消拆除，保留该链接。', '2': '拆除链接，从内存释放并保存到磁盘，保留结构。', '3': '拆除链接并分解脱离部分，只保留 Agent 节点及其上下文、记忆文件，等待复用。'}}
    for label, index, edge in changes:
        getattr(node,label).pop(index)
    saved_id = str(uuid4()) if detached else None
    if detached:
        b.lifecycle['deferred'].append(dict(network_id=saved_id, ids=detached, choice=choice, entry=args['target_node_id'], owner=actor))
    return {'status': 'ok', 'removed': True, 'detached': detached, 'choice': choice, 'saved_network_id': saved_id, 'directory': str(b.directory / 'detached_networks' / saved_id) if saved_id else None}


def decompose(b, p):
    ids = set(p['ids']) - {'root'}
    rows = records(b)
    if ids & reachable(rows):
        raise ValueError('Only root-unreachable fragments may be decomposed')
    pool = b.lifecycle['pool']
    for target in ids:
        binding = b.agents.get(target)
        if binding:
            row = rows[target]
            row['connections'] = {'interfaces': []}
            row['management_parent_id'] = None
            write_record(b, row)
            if target in b.network.nodes:
                b.network.nodes.pop(target)
            binding.update(manager_id=None, managed_ids=[], group_id=None, kind='generic', activity='idle')
            pool[target] = dict(key=binding.get('reuse_key'), eligible=binding.get('reuse_eligible', False))
        else:
            b.network.nodes.pop(target, None)
            b.lifecycle['archived'].pop(target, None)
    for node in b.network.nodes.values():
        for label in ('interfaces',):
            setattr(node, label, [edge for edge in getattr(node, label) if edge.target_node_id not in ids])
        if node.management_parent_id in ids:
            node.management_parent_id = None
    for row in archive_entries(b):
        if row['node_id'] in ids:
            continue
        for label in ('interfaces',):
            row['connections'][label] = [edge for edge in row['connections'][label] if edge['target_node_id'] not in ids]
        if row['management_parent_id'] in ids:
            row['management_parent_id'] = None
        write_record(b, row)
    for binding in b.agents.values():
        if binding.get('manager_id') in ids:
            binding['manager_id'] = None
        binding['managed_ids'] = [id for id in binding.get('managed_ids', []) if id not in ids]
    b.network.delegation_permissions = {source: [target for target in targets if target not in ids] for source, targets in b.network.delegation_permissions.items() if source not in ids}
    for key, group in list(b.lifecycle['offline_groups'].items()):
        if group['board_id'] in ids:
            b.lifecycle['offline_groups'].pop(key)
    for key, group in list(getattr(b, 'groups', {}).items()):
        if group['board'].node_id in ids:
            b.groups.pop(key)
    configure(b)
    return {'pooled': sorted(ids & b.agents.keys())}


def claim(b, p):
    # Backend transactions serialize competing claims.
    candidate = next((id for id, entry in b.lifecycle['pool'].items() if entry['eligible'] and entry['key'] == p['key']), None)
    if candidate is None:
        return {'reused': False, 'node_id': p['target']}
    target = p['target']
    slot = b.network.nodes[target]
    row = next(row for row in archive_entries(b) if row['node_id'] == candidate)
    node = _build({'version':6,'signals':{},'nodes': [row], 'delegations': []}, b.directory).nodes[candidate]
    node.management_parent_id = slot.management_parent_id
    node.interfaces = slot.interfaces
    b.network.nodes.pop(target)
    b.network.add_node(node)
    for other in b.network.nodes.values():
        for links in (other.interfaces,):
            links[:] = [replace(edge, target_node_id=candidate) if edge.target_node_id == target else edge for edge in links]
        if other.management_parent_id == target:
            other.management_parent_id = candidate
        for label, mode in codec_for_node(other).references.items():
            value = getattr(other, label, None)
            if mode == 'many' and value:
                setattr(other, label, [candidate if id == target else id for id in value])
            elif value == target:
                setattr(other, label, candidate)
    b.lifecycle['pool'].pop(candidate)
    b.lifecycle['archived'].pop(candidate)
    b.network.delegation_permissions = {candidate if source == target else source: [candidate if id == target else id for id in targets] for source, targets in b.network.delegation_permissions.items()}
    configure(b)
    return {'reused': True, 'node_id': candidate, 'binding': deepcopy(b.agents[candidate])}


def state(b, p):
    return deepcopy(b.lifecycle)


def archive(b, p):
    id = p['network_id']
    folder = b.directory / 'detached_networks' / id
    folder.mkdir(parents=True, exist_ok=True)
    rows = records(b)
    ids = set(p['ids'])
    manifest = dict(network_id=id, entry_node_id=p['entry'], owner=p['owner'], node_ids=sorted(ids), agent_ids=sorted(ids & b.agents.keys()), status='decomposed' if p['choice'] == 3 else 'saved', directory=str(folder), files=['network.json', 'manifest.json'])
    data = dict(nodes=[rows[target] for target in sorted(ids)], agents={target: b.agents[target] for target in sorted(ids & b.agents.keys())}, groups={key: {k: v for k, v in group.items() if k != 'board'} | {'board_id': group['board'].node_id} for key, group in getattr(b, 'groups', {}).items() if group['board'].node_id in ids})
    manifest['binary_files'] = []
    manifest['resources'] = []
    decoded = _build({'version':6,'signals':{},'nodes': list(rows.values()), 'delegations': []}, b.directory)
    for target in sorted(ids - set(manifest['agent_ids'])):
        for _, label, source in resource_paths(decoded.nodes[target]):
            if not source.is_file():
                continue
            relative = 'resources/' + target.encode().hex() + '/' + label + source.suffix
            destination = folder / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            manifest['binary_files'].append(relative)
            manifest['files'].append(relative)
            manifest['resources'].append(dict(node_id=target, field=label, source=str(source), archived_path=relative))
    for target in manifest['agent_ids']:
        node = b.network.nodes.get(target)
        source = node.file_path if node is not None else b.directory / rows[target]['parameters']['file_path']
        relative = 'memories/' + target.encode().hex() + '.md'
        destination = folder / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text(encoding='utf-8') if source.exists() else '', encoding='utf-8')
        manifest['files'].append(relative)
    for name, value in [('manifest.json', manifest), ('network.json', data)]:
        (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    b.lifecycle['fragments'][id] = manifest
    return {'status': 'ok', 'manifest': manifest}


def inventory(b, p):
    rows = records(b)
    active = reachable(rows)
    result = []
    for fragment in b.lifecycle['fragments'].values():
        if p['actor'] != 'root' and fragment['owner'] != p['actor']:
            continue
        if p.get('network_id') and fragment['network_id'] != p['network_id']:
            continue
        available = [id for id in fragment['agent_ids'] if id in b.lifecycle['pool']]
        result.append({**fragment, 'connected_node_count': len(set(fragment['node_ids']) & active), 'available_agent_ids': available})
    if p.get('network_id') and not result:
        raise PermissionError('Saved network is absent or outside your archive')
    return {'saved_networks': result}


def update(b, p):
    b.lifecycle.update(p)
    return {'ok': True}


def snapshot(b):
    files = {}
    binary_files = {}
    for row in archive_entries(b):
        for label in ('file_path',):
            value = row['parameters'].get(label)
            if value:
                path = (b.directory / value).resolve()
                if path.is_relative_to(b.directory) and path.exists():
                    files[str(path.relative_to(b.directory))] = path.read_text(encoding='utf-8')
    for group in b.lifecycle['offline_groups'].values():
        for name in group.get('archives', []):
            files[name] = (b.directory / name).read_text(encoding='utf-8')
    for name in b.lifecycle['archived'].values():
        files[name] = (b.directory / name).read_text(encoding='utf-8')
    for fragment in b.lifecycle['fragments'].values():
        folder = Path(fragment['directory'])
        for name in fragment['files']:
            path = folder / name
            relative = str(path.relative_to(b.directory))
            if name in fragment.get('binary_files', []):
                binary_files[relative] = base64.b64encode(path.read_bytes()).decode('ascii')
            else:
                files[relative] = path.read_text(encoding='utf-8')
    return {'lifecycle': deepcopy(b.lifecycle), 'files': files, 'lifecycle_binary_files': binary_files}


def restore(b, doc):
    b.lifecycle.update(doc.get('lifecycle', {}))
    for name, content in doc.get('lifecycle_binary_files', {}).items():
        path = (b.directory / name).resolve()
        if not path.is_relative_to(b.directory):
            raise ValueError('Archive resource escapes the network directory')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(content))
    # The checkpoint's complete graph is initially decoded by the core. Parking
    # is deferred until components have restored group references and files.


def register(services):
    services.initializers.append(initialize)
    services.snapshotters.append(snapshot)
    services.restorers.append(restore)
    for name, fn in [('park', park), ('wake', wake), ('interfaces', interfaces), ('decompose', decompose), ('claim', claim), ('update', update)]:
        services.rpc('lifecycle_' + name, fn, mutation=True)
    services.rpc('lifecycle_state', state)
    services.rpc('lifecycle_archive', archive, mutation=True)
    services.rpc('lifecycle_inventory', inventory)
