"""原去中心化组认领、证据表决和退出规则；文件交付由模块完成。"""
from copy import deepcopy
from uuid import uuid4
from time import time
import json
import os
import posixpath
from pathlib import PureWindowsPath

ACTIVE = {"running", "review"}
TERMINAL = {"completed", "failed", "interrupted", "stopped", "budget_exhausted"}


def append(group, actor, kind, content):
    entry = dict(id=str(uuid4()), run_id=group["run_id"], actor=actor, kind=kind, content=content, at=time())
    group["entries"].append(entry)
    return deepcopy(entry)


def complete_candidate(group):
    members = active_members(group)
    candidate = group.get("candidate")
    if group["phase"] == "review" and candidate and members and set(members) <= set(candidate["approvals"]):
        group["phase"] = "completed"


def active_members(g):
    return [member for member in g['members'] if member not in g.get('unavailable', {})]


def live(g):
    if g['phase'] not in ACTIVE:
        raise ValueError('当前小组未运行：' + g['phase'])


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


def claim(group, p):
    g = group
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
        append(g, p['actor'], 'CLAIM', claim_text(item))
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
            append(g, p['actor'], 'CLAIM', claim_text(item))
        return deepcopy(item)
    if p['action'] not in ('complete', 'release'):
        raise ValueError('未知认领操作')
    if p['action'] == 'complete' and not p.get('evidence', '').strip():
        raise ValueError('完成认领须给出验证证据')
    item.update(state='completed' if p['action'] == 'complete' else 'released', evidence=p.get('evidence', ''))
    append(g, p['actor'], 'PATCH_SUMMARY' if p['action'] == 'complete' else 'RELEASE', claim_text(item) + '\n' + item['evidence'])
    return deepcopy(item)


def note(group, p):
    g = group
    live(g)
    if p['kind'] not in ('OBSERVED', 'FACT', 'FAIL', 'PATCH_SUMMARY') or not isinstance(p['content'], str) or not p['content'].strip():
        raise ValueError('记录须有有效 kind 和非空 content')
    return append(g, p['actor'], p['kind'], p['content'])


def finish(group, p):
    g = group
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
            append(g, p['actor'], 'FAIL', '否决成果候选：' + p['evidence'])
            g.update(candidate=None, phase='running')
            return deepcopy(g)
        else:
            raise ValueError('未知验收操作')
    append(g, p['actor'], 'REVIEW', p['evidence'])
    complete_candidate(g)
    return deepcopy(g)


def member_exit(group, p):
    g = group
    actor = p['target']
    if actor not in g['members']:
        raise ValueError('退出节点不是本组成员')
    if g['phase'] not in ACTIVE or actor in g.get('unavailable', {}):
        return deepcopy(g)
    reason = str(p['reason'])
    g.setdefault('unavailable', {})[actor] = dict(status=p.get('status', 'failed'), reason=reason, at=time())
    for item in g['claims'].values():
        if item['actor'] == actor and item['state'] == 'active':
            item.update(state='released', evidence='成员退出本轮：' + reason)
            append(g, actor, 'RELEASE', claim_text(item) + '\n' + item['evidence'])
    append(g, actor, 'MEMBER_EXIT', reason)
    if g.get('candidate'):
        g['candidate']['approvals'].pop(actor, None)
    complete_candidate(g)
    return deepcopy(g)
