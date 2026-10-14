"""Persistent collaboration state; no model loop or Harness dependency."""
from copy import deepcopy
from uuid import uuid4
from time import time
import json
import os
import posixpath
from pathlib import Path, PureWindowsPath
from datanet.services.tools.network_management.templates import expand_package

ACTIVE = {'running', 'review'}
TERMINAL = {'completed', 'failed', 'interrupted', 'stopped', 'budget_exhausted'}


def initialize(b):
    b.cooperative_groups = {}


def snapshot(b):
    files = {name: (b.directory / name).read_text(encoding='utf-8')
             for g in b.cooperative_groups.values() for name in g.get('archives', [])}
    return {'cooperative_groups': b.cooperative_groups, 'cooperative_run_files': files}


def restore(b, document):
    b.cooperative_groups = deepcopy(document.get('cooperative_groups', {}))
    from datanet.components.nodes.text_file_node.text_file_node import TextFileNode
    for name, content in document.get('cooperative_run_files', {}).items():
        path = (b.directory / name).resolve()
        if not path.is_relative_to(b.directory / 'cooperation'):
            raise ValueError('协作归档路径超出存储目录')
        path.parent.mkdir(parents=True, exist_ok=True)
        TextFileNode._atomic_bytes(path, content.encode('utf-8'))


def prepare(b, p):
    if not isinstance(p.get('project'), str) or not p['project'].strip():
        raise ValueError('去中心化小组须填写非空 project，包含目标、约束和验收标准')
    return None


def package(b, p, state):
    owner = b.components.catalog['network_presets/decentralized_group']['directory']
    spec = json.loads((owner / 'members.json').read_text(encoding='utf-8'))
    return expand_package(owner / 'package.json', p, b.directory, spec)[0]


def finalize(b, p, result, state):
    if result.status != 'ok':
        return result
    ids = result.items[0]['node_ids']
    group = dict(group_id=p['instance_id'], owner=p['actor'], members=[id for name, id in ids.items() if name.startswith('worker_')],
                 entry_points=result.items[0]['entry_points'], phase='ready', run_id=None, task=None,
                 claims={}, entries=[], candidate=None, requests={}, jobs={}, notified=False, failure=None)
    b.cooperative_groups[group['group_id']] = group
    b.network.nodes[ids['project']].write('content', p['project'])
    return dict(status='ok', group_id=group['group_id'], member_count=len(group['members']), members=group['members'],
                entry_points=group['entry_points'], structure=b.created_structure(result.items[0]))


def get(b, p, member=False):
    g = b.cooperative_groups.get(p['group_id'])
    if not g:
        raise ValueError('未知去中心化小组')
    actor = p['actor']
    if member:
        if actor not in g['members']:
            raise PermissionError('仅本组成员可调用协作工具')
    elif actor not in g['members']:
        reachable = {n.node_id for n, _ in b.network.walk(actor, direction='read', strength=p.get('strength', 2))}
        if g['entry_points']['board'] not in reachable:
            raise PermissionError('小组不在调用者的读取范围内')
    return g


def live(g):
    if g['phase'] not in ACTIVE:
        raise ValueError('当前小组未运行：' + g['phase'])


def append(b, g, actor, kind, content):
    entry = dict(id=str(uuid4()), run_id=g['run_id'], actor=actor, kind=kind, content=content, at=time())
    g['entries'].append(entry)
    path = g['entry_points']['findings']
    b.network.nodes[path].write('content', json.dumps(entry, ensure_ascii=False) + '\n', mode='append')
    return deepcopy(entry)


def status(b, p):
    g = get(b, p)
    result = deepcopy(g)
    query = p.get('query')
    result['entries'] = [e for e in result['entries'] if query.casefold() in e['content'].casefold() or query == e['id']] if query else result['entries'][-20:]
    result['entry_count'] = len(g['entries'])
    result['workspace'] = str(Path(g['workspace_directory']) / 'main') if g.get('workspace_directory') else str(b.directory / 'cooperation' / g['group_id'].encode().hex() / 'workspace')
    if result.get('archive_path'):
        result['archive_path'] = str(b.directory / result['archive_path'])
    for record in result.get('runs', {}).values():
        record['archive_path'] = str(b.directory / record['archive_path'])
    return result


def archive_run(b, g):
    if not g.get('run_id'):
        return
    if g['run_id'] in g.get('runs', {}):
        return
    directory = b.directory / 'cooperation' / g['group_id'].encode().hex() / 'runs' / g['run_id']
    directory.mkdir(parents=True, exist_ok=True)
    record = {key: deepcopy(g.get(key)) for key in ('run_id', 'task', 'phase', 'failure', 'claims', 'entries', 'candidate', 'requests', 'jobs', 'report_reference')}
    writer = b.network.nodes[g['entry_points']['output']]
    for name, target in [('output.md', 'output'), ('findings.md', 'findings')]:
        node = b.network.nodes[g['entry_points'][target]]
        path = directory / name
        writer._atomic_bytes(path, node.file_path.read_bytes() if node.file_path.exists() else b'')
        record[name] = str(path.relative_to(b.directory))
    path = directory / 'run.json'
    writer._atomic_bytes(path, json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8'))
    g['archive_path'] = str(directory.relative_to(b.directory))
    files = [str((directory / name).relative_to(b.directory)) for name in ('run.json', 'output.md', 'findings.md')]
    g['archives'] = list(dict.fromkeys([*g.get('archives', []), *files]))
    g.setdefault('runs', {})[g['run_id']] = dict(run_id=g['run_id'], task=g['task'], phase=g['phase'],
                                               archive_path=g['archive_path'], report_reference=g.get('report_reference'))


def start(b, p):
    g = get(b, p)
    if p['actor'] in g['members']:
        raise PermissionError('由网络调用者启动或停止小组')
    if g['phase'] not in TERMINAL | {'ready'}:
        raise ValueError('小组已经启动，使用 status 查看或 stop 收尾')
    if not isinstance(p.get('task'), str) or not p['task'].strip():
        raise ValueError('start 必须提供非空 task')
    minutes = p.get('budget_minutes', 30)
    if isinstance(minutes, bool) or not isinstance(minutes, (float, int)) or not .1 <= minutes <= 1440:
        raise ValueError('budget_minutes 须在 0.1 至 1440 之间')
    archive_run(b, g)
    for target in ('output', 'findings'):
        b.network.nodes[g['entry_points'][target]].write('content', '')
    g.update(phase='running', caller=p['actor'], task=p['task'], run_id=str(uuid4()), started_at=time(), deadline=time() + minutes * 60,
             claims={}, entries=[], candidate=None, requests={}, jobs={}, notified=False, failure=None,
             archive_path=None, report_reference=None)
    return deepcopy(g)


def update(b, p):
    g = b.cooperative_groups[p['group_id']]
    for field in ('jobs', 'notified', 'failure', 'phase', 'report_reference', 'workspace_directory'):
        if field in p:
            g[field] = deepcopy(p[field])
    if 'phase' in p and g['phase'] in TERMINAL:
        archive_run(b, g)
    return deepcopy(g)


def claim_paths(value):
    if not isinstance(value, list):
        raise ValueError('paths 须为工作区相对路径列表')
    paths, seen = [], set()
    for raw in value:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError('paths 须为非空路径字符串列表')
        raw = raw.strip().replace('\\', '/')
        if raw.startswith('/') or PureWindowsPath(raw).drive:
            raise ValueError('paths 使用工作区相对路径')
        path = posixpath.normpath(raw)
        if os.name == 'nt':
            path = '/'.join(part.rstrip(' .') if part not in ('.', '..') else part for part in path.split('/'))
        if not path or path in ('.', '..') or path.startswith('../') or any(not part or part.casefold() == '.git' for part in path.split('/')) or any(char in path for char in '\0*?[]:'):
            raise ValueError('paths 须指向工作区内的文件或目录，不使用通配符或 .git')
        key = os.path.normcase(path)
        if key not in seen:
            paths.append(path)
            seen.add(key)
    return paths


def claim_conflict(g, scope, paths, exclude=None):
    for entry in g['claims'].values():
        if entry['state'] != 'active' or entry['id'] == exclude:
            continue
        if entry['scope'].casefold() == scope.casefold():
            return dict(conflict=True, reason='scope', claim=deepcopy(entry))
        overlaps = []
        for requested in paths:
            left = os.path.normcase(requested)
            for claimed in entry.get('paths', []):
                right = os.path.normcase(claimed)
                # A directory claim also covers its descendants, but not name prefixes.
                if left == right or left.startswith(right + os.sep) or right.startswith(left + os.sep):
                    overlaps.append(dict(requested=requested, claimed=claimed))
        if overlaps:
            return dict(conflict=True, reason='paths', claim=deepcopy(entry), overlaps=overlaps)
    return None


def claim_text(item):
    return item['scope'] + ('\npaths=' + json.dumps(item['paths'], ensure_ascii=False) if item.get('paths') else '')


def claim(b, p):
    g = get(b, p, True)
    live(g)
    if p['action'] == 'claim':
        if g['phase'] != 'running':
            raise ValueError('成果正在验收，否决候选后再认领新任务')
        scope = p.get('scope', '').strip()
        if not scope:
            raise ValueError('认领须提供 scope')
        paths = claim_paths(p.get('paths', []))
        conflict = claim_conflict(g, scope, paths)
        if conflict:
            return conflict
        id = str(uuid4())
        item = dict(id=id, actor=p['actor'], scope=scope, paths=paths, state='active', evidence='')
        g['claims'][id] = item
        append(b, g, p['actor'], 'CLAIM', claim_text(item))
        return deepcopy(item)
    item = g['claims'].get(p.get('claim_id'))
    if not item or item['actor'] != p['actor'] or item['state'] != 'active':
        raise PermissionError('只能操作自己仍有效的认领')
    if p['action'] == 'extend':
        if g['phase'] != 'running':
            raise ValueError('成果正在验收，否决候选后再补充认领')
        paths = claim_paths([*item.get('paths', []), *claim_paths(p.get('paths'))])
        conflict = claim_conflict(g, item['scope'], paths, item['id'])
        if conflict:
            return conflict
        if paths != item.get('paths', []):
            item['paths'] = paths
            append(b, g, p['actor'], 'CLAIM', claim_text(item))
        return deepcopy(item)
    if p['action'] not in ('complete', 'release'):
        raise ValueError('未知认领操作')
    if p['action'] == 'complete' and not p.get('evidence', '').strip():
        raise ValueError('完成认领须给出验证证据')
    item.update(state='completed' if p['action'] == 'complete' else 'released', evidence=p.get('evidence', ''))
    append(b, g, p['actor'], 'PATCH_SUMMARY' if p['action'] == 'complete' else 'RELEASE', claim_text(item) + '\n' + item['evidence'])
    return deepcopy(item)


def note(b, p):
    g = get(b, p, True)
    live(g)
    if p['kind'] not in ('OBSERVED', 'FACT', 'FAIL', 'PATCH_SUMMARY') or not isinstance(p['content'], str) or not p['content'].strip():
        raise ValueError('记录须有有效 kind 和非空 content')
    return append(b, g, p['actor'], p['kind'], p['content'])


def finish(b, p):
    g = get(b, p, True)
    live(g)
    if not isinstance(p.get('evidence'), str) or not p['evidence'].strip():
        raise ValueError('验收须说明证据或否决理由')
    if p['action'] == 'propose':
        if g['candidate'] or any(c['state'] == 'active' for c in g['claims'].values()):
            raise ValueError('已有成果候选或仍有未结束的认领')
        if not p.get('content', '').strip():
            raise ValueError('提出候选须提供最终成果正文')
        review = p.get('review')
        g['candidate'] = dict(id=review['id'] if review else str(uuid4()), content=p['content'], approvals={p['actor']: p['evidence']}, review=deepcopy(review))
        g['phase'] = 'review'
    else:
        c = g['candidate']
        if not c or p.get('candidate_id') != c['id']:
            raise ValueError('成果候选已变化，请读取当前 candidate_id')
        if p['action'] == 'approve':
            c['approvals'][p['actor']] = p['evidence']
        elif p['action'] == 'reject':
            append(b, g, p['actor'], 'FAIL', '否决成果候选：' + p['evidence'])
            g.update(candidate=None, phase='running')
            return deepcopy(g)
        else:
            raise ValueError('未知验收操作')
    append(b, g, p['actor'], 'REVIEW', p['evidence'])
    if set(g['candidate']['approvals']) == set(g['members']):
        b.network.nodes[g['entry_points']['output']].write('content', g['candidate']['content'])
        g['phase'] = 'completed'
        archive_run(b, g)
    return deepcopy(g)


def stop(b, p):
    g = b.cooperative_groups[p['group_id']]
    if p['actor'] != g.get('caller'):
        raise PermissionError('由本次协作调用者停止小组')
    if g['phase'] in ACTIVE:
        g.update(phase=p.get('phase', 'stopped'), failure=p.get('failure'))
        archive_run(b, g)
    return deepcopy(g)


def register(s):
    for name, function in [('cooperative_status', status), ('cooperative_start', start), ('cooperative_update', update),
                           ('cooperative_claim', claim), ('cooperative_note', note), ('cooperative_finish', finish), ('cooperative_stop', stop)]:
        s.rpc(name, function, mutation=name != 'cooperative_status')
    s.initializers.append(initialize)
    s.snapshotters.append(snapshot)
    s.restorers.append(restore)
    owner = s.catalog['network_presets/decentralized_group']['directory']
    s.network_presets['decentralized_group'] = owner / 'package.json'
    s.network_handlers['decentralized_group'] = dict(entry_point='board', prepare=prepare, package=package, finalize=finalize)
    s.statusters.append(lambda b: {'cooperative_groups': {id: dict(phase=g['phase'], members=g['members'], run_id=g['run_id']) for id, g in b.cooperative_groups.items()}})
