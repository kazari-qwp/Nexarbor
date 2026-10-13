from datanet.services.nodes.text.services import bindings
from datanet.core.node import NodeResult
from datanet.core.interface import Interface
from uuid import uuid4
from datanet.components.networks.discussion_group.setup import storage_toolkits
from datanet.components.nodes.text_file_node.text_file_node import TextFileNode
from datanet.components.nodes.discussion_board_node.discussion_board_node import DiscussionBoardNode

def recovery_info(self, p):
    summaries = {}
    for key, g in self.groups.items():
        members = g['board'].members
        completed = g.get('completed', False)
        phase = 'completed' if completed else 'round_in_progress' if g['busy'] else 'finalizing' if g['round'] >= g['total'] else 'ready'
        summaries[key] = {'group_id': key, 'members': members, 'leader_id': g['board'].leader_id, 'recorder_id': g['board'].recorder_id, 'completed': completed, 'busy': g['busy'], 'phase': phase, 'round': g['round'], 'total_rounds': g['total'], 'completed_rounds': g['round'] - int(g['busy']), 'submitted_members': list(g['submitted']), 'remaining_members': [m for m in members if m not in g['submitted']] if g['busy'] else [], 'task': g.get('task'), 'output_id': g['board'].output_id, 'last_error': g.get('last_error'), 'next_action': '读取最终成果，无需重跑' if completed else '继续未提交成员，再归档本轮' if g['busy'] else '所有讨论轮次已归档，仅继续Recorder收尾，无需重新讨论' if phase == 'finalizing' else '继续下一轮讨论' if g.get('task') else '提供任务并开始讨论', 'resume': {'tool': 'datanet_discuss', 'arguments': {'group_id': key}} if g.get('task') and (not completed) else None}
    return {'node_count': len(self.network.nodes), 'agents': self.agents, 'groups': summaries, 'management': {key: node.management_parent_id for key, node in self.network.nodes.items()}, 'unassigned_management_nodes': [key for key, node in self.network.nodes.items() if key != self.root.node_id and node.management_parent_id is None], 'feedback': getattr(self,'feedback',[]), 'pending_operations': self.store.pending(), 'checkpoint_count': self.store.db.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0]}

def group_task(self, p):
    group(self, p['group_id'])['task'] = p['task']
    return {'ok': True}

def group_error(self, p):
    group(self, p['group_id'])['last_error'] = p['error']
    return {'ok': True}

def group_complete(self, p):
    group(self, p['group_id'])['last_error'] = None
    group(self, p['group_id'])['completed'] = True
    return {'ok': True}

def start_round(self, p):
    g = group(self, p['group_id'])
    board = g['board']
    if g['busy']:
        return {'round': g['round'], 'total': g['total'], 'snapshot': board._read_key('content').items[0]['content'], 'submitted': g['submitted']}
    if g['round'] >= g['total']:
        raise ValueError('all rounds completed')
    board = g['board']
    if board.file_path.exists() and board.file_path.read_bytes():
        raise ValueError('unarchived submissions exist')
    g['round'] += 1
    g['busy'] = True
    g['submitted'] = {}
    board.current_round, board.total_rounds = (g['round'], g['total'])
    return {'round': g['round'], 'total': g['total'], 'snapshot': board._read_key('content').items[0]['content']}

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
    if not g['busy'] or member not in g['board'].members or member in g['submitted']:
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
    if not g['busy'] or set(g['submitted']) != set(g['board'].members):
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
    return {'members': b.members, 'recorder_id': b.recorder_id, 'project_id': b.project_id, 'project_ids': b.project_ids, 'board_id': b.node_id, 'notebook_id': b.notebook_id, 'output_id': b.output_id, 'round': g['round'], 'total': g['total'], 'busy': g['busy'], 'submitted': g['submitted'], 'completed': g.get('completed', False), 'task': g.get('task')}

def register(services):
    services.rpc('group_task', group_task, mutation=True)
    services.rpc('group_error', group_error, mutation=True)
    services.rpc('group_complete', group_complete, mutation=True)
    services.rpc('start_round', start_round, mutation=True)
    services.rpc('read_round', read_round, mutation=False)
    services.rpc('submit', submit, mutation=True)
    services.rpc('finish_round', finish_round, mutation=True)
    services.rpc('group_info', group_info, mutation=False)

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
    return project_sources(backend, p)

def finalize(backend, p, result, refs):
    if result.status != 'ok':
        return result
    board = backend.network.nodes[result.items[0]['entry_points']['board']]
    group_id = p['instance_id']
    backend.groups[group_id] = {'board': board, 'round': 0, 'total': p.get('rounds', 8), 'submitted': {}, 'busy': False, 'run': uuid4().hex, 'archives': [], 'completed': False}
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
    return {'status': 'ok', 'group_id': group_id, 'members': board.members, 'leader_id': board.leader_id, 'recorder_id': board.recorder_id, 'entry_points': result.items[0]['entry_points'], 'structure': backend.created_structure(result.items[0])}

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
    for group in backend.groups.values():
        board = group['board']
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
    services.network_handlers['discussion_group'] = {'entry_point': 'board', 'prepare': prepare, 'finalize': finalize}
    services.toolkit_factories.append(lambda backend: storage_toolkits(backend.directory / 'groups'))
