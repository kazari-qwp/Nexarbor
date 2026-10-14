from datanet.services.nodes.text.services import bindings, label
from datanet.core.node import NodeResult
from datanet.core.interface import Interface
from uuid import uuid4
import json
from datanet.components.networks.discussion_group.setup import storage_toolkits
from datanet.components.nodes.text_file_node.text_file_node import TextFileNode
from datanet.components.nodes.discussion_board_node.discussion_board_node import DiscussionBoardNode

def recovery_info(self, p):
    summaries = {}
    for key, g in self.groups.items():
        members = g['board'].members
        completed = g.get('completed', False)
        phase = 'completed' if completed else 'round_in_progress' if g['busy'] else 'finalizing' if g['round'] >= g['total'] else 'ready'
        summaries[key] = {'group_id': key, 'members': members, 'leader_id': g['board'].leader_id, 'recorder_id': g['board'].recorder_id, 'completed': completed, 'busy': g['busy'], 'phase': phase, 'round': g['round'], 'total_rounds': g['total'], 'completed_rounds': g['round'] - int(g['busy']), 'submitted_members': list(g['submitted']), 'unavailable': g.get('unavailable', {}), 'remaining_members': [m for m in members if m not in g['submitted'] and m not in g.get('unavailable', {})] if g['busy'] else [], 'task': g.get('task'), 'output_id': g['board'].output_id, 'last_error': g.get('last_error'), 'next_action': '读取本次成果，或提供 task 开始新任务' if completed else '继续未提交成员，再归档本轮' if g['busy'] else '所有讨论轮次已归档，仅继续Recorder收尾，无需重新讨论' if phase == 'finalizing' else '继续下一轮讨论' if g.get('task') else '提供任务并开始讨论', 'resume': {'tool': 'datanet_discuss', 'arguments': {'group_id': key}} if g.get('task') and (not completed) else None}
    return {'node_count': len(self.network.nodes), 'agents': self.agents, 'groups': summaries, 'management': {key: node.management_parent_id for key, node in self.network.nodes.items()}, 'unassigned_management_nodes': [key for key, node in self.network.nodes.items() if key != self.root.node_id and node.management_parent_id is None], 'feedback': getattr(self,'feedback',[]), 'pending_operations': self.store.pending(), 'checkpoint_count': self.store.db.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0]}

def group_task(self, p):
    group(self, p['group_id'])['task'] = p['task']
    return {'ok': True}

def archive_run(self, g):
    if not g.get('task'):
        return
    if g['run'] in g.get('runs', {}):
        return
    board = g['board']
    directory = board.file_path.parent / 'archive' / g['run']
    directory.mkdir(parents=True, exist_ok=True)
    record = {key: g.get(key) for key in ('run', 'task', 'completed', 'round', 'total', 'last_error', 'report_reference', 'unavailable', 'loss_notice_sent', 'caller')}
    for name, target in [('result.md', board.output_id), ('notebook.md', board.notebook_id)]:
        node = self.network.nodes[target]
        path = directory / name
        board._atomic_bytes(path, node.file_path.read_bytes() if node.file_path.exists() else b'')
        relative = str(path.relative_to(self.directory))
        if relative not in g['archives']:
            g['archives'].append(relative)
        record[name] = relative
    path = directory / 'run.json'
    board._atomic_bytes(path, json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8'))
    relative = str(path.relative_to(self.directory))
    if relative not in g['archives']:
        g['archives'].append(relative)
    g['archive_path'] = str(directory.relative_to(self.directory))
    runs = g.setdefault('runs', {})
    runs[g['run']] = record

def begin(self, p):
    g = group(self, p['group_id'])
    task = p['task']
    if not isinstance(task, str) or not task.strip():
        raise ValueError('New discussion requires a nonempty task')
    if not g.get('completed') and g.get('task') and g['task'] != task:
        raise ValueError('Recovered discussion must continue its saved task')
    if g.get('completed'):
        archive_run(self, g)
        board = g['board']
        board._atomic_bytes(board.file_path, b'')
        board._atomic_bytes(board.previous_path, b'')
        for target in (board.notebook_id, board.output_id):
            self.network.nodes[target].write('content', '')
        g.update(run=uuid4().hex, round=0, submitted={}, busy=False, completed=False,
                 last_error=None, archive_path=None, report_reference=None, unavailable={}, loss_notice_sent=False)
        board.current_round = 0
    g['task'] = task
    g['caller'] = p.get('caller', g.get('caller'))
    return group_info(self, p)

def group_error(self, p):
    group(self, p['group_id'])['last_error'] = p['error']
    return {'ok': True}

def group_complete(self, p):
    g = group(self, p['group_id'])
    g.update(last_error=None, completed=True, report_reference=p.get('report_reference'))
    archive_run(self, g)
    return {'ok': True, 'run_id': g['run'], 'archive_path': str(self.directory / g['archive_path'])}

def start_round(self, p):
    g = group(self, p['group_id'])
    board = g['board']
    if not g['busy'] or 'notebook_snapshot' not in g:
        notebook = self.network.nodes[board.notebook_id]
        content = notebook._read_key('content')
        g['notebook_snapshot'] = label(notebook) + '\n' + (content.items[0]['content'] if content.status == 'ok' else '')
    if g['busy']:
        return {'round': g['round'], 'total': g['total'], 'snapshot': board._read_key('content').items[0]['content'], 'submitted': g['submitted'], 'notebook_snapshot': g['notebook_snapshot']}
    if g['round'] >= g['total']:
        raise ValueError('all rounds completed')
    board = g['board']
    if board.file_path.exists() and board.file_path.read_bytes():
        raise ValueError('unarchived submissions exist')
    g['round'] += 1
    g['busy'] = True
    g['submitted'] = {}
    board.current_round, board.total_rounds = (g['round'], g['total'])
    return {'round': g['round'], 'total': g['total'], 'snapshot': board._read_key('content').items[0]['content'], 'notebook_snapshot': g['notebook_snapshot']}

def read_round(self, p):
    g = group(self, p['group_id'])
    if p['actor'] not in g['board'].members:
        raise PermissionError('Only discussion members may read round snapshots')
    if not any((node.node_id == g['board'].node_id for node, _ in self.network.walk(p['actor'], direction='read', strength=p.get('strength', 2)))):
        raise PermissionError('Discussion board is not read-reachable')
    return g['board']._read_key('content')

def submit(self, p):
    g = group(self, p['group_id'])
    member = p['actor']
    if not g['busy'] or member not in g['board'].members or member in g.get('unavailable', {}) or member in g['submitted']:
        raise ValueError('not an active member or already submitted')
    content = p.get('content', '')
    if not isinstance(content, str) or (not p.get('skip') and (not content.strip())):
        raise ValueError('empty submission')
    if p.get('skip'):
        content = '[跳过] ' + content
    if not any((node.node_id == g['board'].node_id for node, _ in self.network.walk(member, direction='write', strength=2))):
        return NodeResult(status='forbidden', errors=['讨论黑板不在成员写入范围内'])
    result = g['board']._append_submission('content', f"\n## 第{g['round']}轮 · {member}\n{content}\n", mode='append')
    if result.status != 'ok':
        return result
    g['submitted'][member] = content
    return {'status': 'ok', 'submitted': True, 'content': content}

def finish_round(self, p):
    g = group(self, p['group_id'])
    required = set(g['board'].members) - set(g.get('unavailable', {}))
    if not g['busy'] or not required <= set(g['submitted']):
        raise ValueError('round incomplete')
    path = g['board'].file_path.parent / 'archive' / g['run'] / f"round_{g['round']:03d}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    g['board']._finish_round(path)
    g['busy'] = False
    g.setdefault('archives', []).append(str(path.relative_to(self.directory)))
    return {'round': g['round'], 'archive_path': str(path), 'submissions': g['submitted']}

def group_info(self, p):
    g = group(self, p['group_id'])
    b = g['board']
    return {'members': b.members, 'active_members': [m for m in b.members if m not in g.get('unavailable', {})], 'unavailable': g.get('unavailable', {}), 'loss_notice_sent': g.get('loss_notice_sent', False), 'owner': g.get('owner'), 'caller': g.get('caller'), 'leader_id': b.leader_id, 'recorder_id': b.recorder_id, 'project_id': b.project_id, 'project_ids': b.project_ids, 'board_id': b.node_id, 'notebook_id': b.notebook_id, 'output_id': b.output_id, 'round': g['round'], 'total': g['total'], 'busy': g['busy'], 'submitted': g['submitted'], 'completed': g.get('completed', False), 'task': g.get('task'), 'run_id': g['run'], 'archive_path': str(self.directory / g['archive_path']) if g.get('archive_path') else None, 'runs': g.get('runs', {})}

def register(services):
    services.rpc('group_begin', begin, mutation=True)
    services.rpc('group_task', group_task, mutation=True)
    services.rpc('group_error', group_error, mutation=True)
    services.rpc('group_complete', group_complete, mutation=True)
    services.rpc('discussion_member_exit', member_exit, mutation=True)
    services.rpc('discussion_loss_notice', loss_notice, mutation=True)
    services.rpc('start_round', start_round, mutation=True)
    services.rpc('read_round', read_round, mutation=False)
    services.rpc('submit', submit, mutation=True)
    services.rpc('finish_round', finish_round, mutation=True)
    services.rpc('group_info', group_info, mutation=False)

def member_exit(self, p):
    g = group(self, p['group_id'])
    board, member = g['board'], p['target']
    if member not in board.members or member in (board.leader_id, board.recorder_id):
        raise ValueError('仅普通讨论成员可退出本轮讨论')
    if member not in g.setdefault('unavailable', {}):
        g['unavailable'][member] = dict(reason=str(p['reason']), at=__import__('time').time())
        if g['busy']:
            board._append_submission('content', f"\n## 第{g['round']}轮 · 成员退出：{member}\n{p['reason']}\n", mode='append')
    return group_info(self, p)


def loss_notice(self, p):
    g = group(self, p['group_id'])
    g['loss_notice_sent'] = p['sent']
    return {'ok': True}


def group(backend, group_id):
    if group_id not in backend.groups:
        raise ValueError('unknown group')
    return backend.groups[group_id]

def initialize(backend):
    backend.groups = {}

def snapshot(backend):
    groups = {key: {k: v for k, v in value.items() if k != 'board'} | {'board_id': value['board'].node_id} for key, value in backend.groups.items()}
    files = {name: (backend.directory / name).read_text(encoding='utf-8') for value in backend.groups.values() for name in value.get('archives', [])}
    return {'groups': groups, 'files': files}

def restore(backend, document):
    for key, value in document.get('groups', {}).items():
        if value['board_id'] not in backend.network.nodes:
            continue
        board = backend.network.nodes[value['board_id']]
        backend.groups[key] = {k: v for k, v in value.items() if k != 'board_id'} | {'board': board}
        board.current_round, board.total_rounds = (value['round'], value['total'])

def restore_node(backend, node, document):
    if isinstance(node, DiscussionBoardNode):
        node.bind_network(backend.network)
        node.attach_member_tools()
        node.tools.pop('run_discussion', None)
        node.tool_definitions.pop('run_discussion', None)

def prepare(backend, p):
    if type(p.get('rounds', 8)) is not int or not 1 <= p.get('rounds', 8) <= 8:
        raise ValueError('rounds 须为 1 至 8 的整数')
    return project_sources(backend, p)

def package(backend, p, refs):
    from datanet.services.tools.network_management.templates import expand_package
    owner = backend.components.catalog['network_presets/discussion_group']['directory']
    spec = __import__('json').loads((owner / 'members.json').read_text(encoding='utf-8'))
    path, _ = expand_package(backend.components.network_presets['discussion_group'], p, backend.directory, spec)
    return path

def finalize(backend, p, result, refs):
    if result.status != 'ok':
        return result
    board = backend.network.nodes[result.items[0]['entry_points']['board']]
    group_id = p['instance_id']
    backend.groups[group_id] = {'board': board, 'round': 0, 'total': p.get('rounds', 8), 'submitted': {}, 'busy': False, 'run': uuid4().hex, 'archives': [], 'completed': False, 'owner': p['actor'], 'unavailable': {}, 'loss_notice_sent': False}
    if refs is not None:
        connect_project(backend, board, refs)
        result.items[0]['node_ids'] = {k: v for k, v in result.items[0]['node_ids'].items() if v in backend.network.nodes}
        result.items[0]['entry_points'].pop('project', None)
        result.items[0]['entry_points']['projects'] = list(refs)
    else:
        written = backend.network.nodes[board.project_id].write('content', p['project'])
        if written.status != 'ok':
            return written
    board.tools.pop('run_discussion', None)
    board.tool_definitions.pop('run_discussion', None)
    return {'status': 'ok', 'group_id': group_id, 'member_count': len(board.members) - 2, 'members': board.members, 'leader_id': board.leader_id, 'recorder_id': board.recorder_id, 'entry_points': result.items[0]['entry_points'], 'structure': backend.created_structure(result.items[0])}

def load_project(backend, p):
    board = group(backend, p['group_id'])['board']
    if p['actor'] not in board.members:
        raise PermissionError('仅讨论成员可首次加载本组资料')
    allowed = {n.node_id for n in bindings(backend, p) if n.delivery == 'query'}
    if not set(board.project_ids) <= allowed:
        raise PermissionError('成员缺少项目资料读取连接')
    return board.invoke_tool('load_project')

def extra_status(backend):
    return {'groups': recovery_info(backend, {})['groups']}

def project_sources(backend, p):
    refs = p.get('project_nodes')
    if refs is not None:
        if not isinstance(refs, list) or not refs or (not all((isinstance(x, str) and x for x in refs))) or (len(set(refs)) != len(refs)):
            raise ValueError('project_nodes 必须为不重复的非空查询文本节点ID列表')
        if 'project' in p:
            raise ValueError('project_nodes 与 project 只选一种')
        reachable = {n.node_id for n, _ in backend.network.walk(p.get('actor', 'root'), direction='read', strength=p.get('strength', 0))}
        for target in refs:
            node = backend.network.nodes.get(target)
            if not isinstance(node, TextFileNode) or node.delivery != 'query' or target not in reachable:
                raise PermissionError('项目资料须为创建者可读取的查询文本节点：' + target)
        return refs
    if not isinstance(p.get('project'), str) or not p['project'].strip():
        raise ValueError('未提供 project_nodes 时必须填写非空 project')
    return None

def connect_project(backend, board, refs):
    old = board.project_id
    for node in backend.network.nodes.values():
        for direction in ('read', 'write'):
            attr = direction + '_interfaces'
            setattr(node, attr, [edge for edge in getattr(node, attr) if edge.target_node_id != old])
    backend.network.nodes.pop(old)
    for actor in [board.node_id, *board.members]:
        node = backend.network.nodes[actor]
        node.read_interfaces.extend((Interface(target, visibility='private') for target in refs))
    board.project_ids = list(refs)
    board.project_id = refs[0]

def migrate(backend):
    from datanet.services.tools.network_management.services import ensure_agent_node
    for group in backend.groups.values():
        board = group['board']
        removed = set()
        for actor in board.members:
            ensure_agent_node(backend, {'target': actor})
            old_notes = backend.network.nodes.get(actor + '_notes')
            if old_notes is not None:
                result = old_notes.read({'method': 'key', 'key': 'content'})
                if result.status == 'ok' and result.items:
                    backend.network.nodes[actor].write_memory(result.items[0]['content'], 'append')
                removed.add(old_notes.node_id)
        for target in removed:
            backend.network.nodes.pop(target)
        for node in backend.network.nodes.values():
            for direction in ('read', 'write'):
                links = getattr(node, direction + '_interfaces')
                links[:] = [edge for edge in links if edge.target_node_id not in removed]
        for target in board.project_ids:
            backend.network.nodes[target].delivery = 'query'
        notebook = backend.network.nodes[board.notebook_id]
        notebook.delivery = 'resident'
        notebook.name = '公共笔记'
        notebook.description = '由recorder维护'
        notebook.tools.pop('read', None)
        notebook.tool_definitions.pop('read', None)
        notebook.expose = [x for x in notebook.expose if x != 'read']
        for actor in board.members:
            node = backend.network.nodes[actor]
            for target in [*board.project_ids, board.notebook_id]:
                if not any((e.target_node_id == target for e in node.read_interfaces)):
                    node.read_interfaces.append(Interface(target, visibility='private'))
register_routes = register

def register(services):
    register_routes(services)
    services.rpc('load_project', load_project)
    services.initializers.append(initialize)
    services.snapshotters.append(snapshot)
    services.restorers.append(restore)
    services.node_restorers.append(restore_node)
    services.migrations.append(migrate)
    services.statusters.append(extra_status)
    services.network_presets['discussion_group'] = services.catalog['network_presets/discussion_group']['directory'] / 'python/datanet/components/networks/discussion_group/package.json'
    services.network_handlers['discussion_group'] = {'entry_point': 'board', 'prepare': prepare, 'package': package, 'finalize': finalize}
    services.toolkit_factories.append(lambda backend: storage_toolkits(backend.directory / 'groups'))
