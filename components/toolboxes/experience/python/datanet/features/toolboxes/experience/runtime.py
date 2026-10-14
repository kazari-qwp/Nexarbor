from copy import deepcopy
from uuid import uuid4
from datanet.core.application import Component
from datanet.core.state_store import JsonStore
from datanet.core.record_values import now

KINDS = {'common', 'tool', 'toolbox', 'role', 'node'}

def validate(p):
    def text(name, maximum):
        value = p.get(name)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError('Invalid ' + name)
        return value.strip()
    applies = p.get('applies')
    if not isinstance(applies, list) or not 1 <= len(applies) <= 12 or any(a.get('kind') not in KINDS or not isinstance(a.get('id'), str) or not a['id'].strip() or len(a['id']) > 160 for a in applies):
        raise ValueError('Invalid experience selectors')
    return dict(applies=deepcopy(applies), trigger=text('trigger', 240), advice=text('advice', 1000), evidence=text('evidence', 1000), version=text('version', 100), core=p.get('core') is True)


class Plugin(Component):
    def install(self):
        self.store = JsonStore(self.r.config.get('experienceDirectory', self.r.directory / 'experiences') / 'library.json' if not isinstance(self.r.config.get('experienceDirectory'), str) else self.r.config['experienceDirectory'] + '/library.json', dict(format=1, entries=[], reviews=[]))
        seed = self.r.resource(self.id, 'seed.json', json_data=True)
        def initial(db):
            for entry in seed:
                if not any(e['id'] == entry['id'] for e in db['entries']):
                    db['entries'].append(dict(**validate(entry), id=entry['id'], status='verified', author='framework', reviewer='framework', created_at=now()))
        self.store.mutate(initial)
        self.views = {}
        self.on('agent/bound', self.bound)
        self.on('context/prepare', self.prepare)
        self.on('tool/native-before', self.use)
        self.on('tool/before', self.use)

    def query(self, p):
        limit, offset, status = p.get('limit', 6), p.get('offset', 0), p.get('status', 'all')
        if type(limit) is not int or not 1 <= limit <= 10 or type(offset) is not int or offset < 0 or status not in ('all', 'verified', 'pending', 'retired', 'rejected', 'merged'):
            raise ValueError('Invalid experience query')
        entries = []
        for entry in self.store.data['entries']:
            if p.get('core_only') and not entry.get('core'):
                continue
            if entry['status'] not in (('verified', 'pending') if status == 'all' else (status,)):
                continue
            if p.get('ids') and entry['id'] not in p['ids'] or entry['id'] in p.get('exclude_ids', []):
                continue
            if p.get('selectors') and not any(a == s for a in entry['applies'] for s in p['selectors']):
                continue
            haystack = str([entry['trigger'], entry['advice'], entry['applies']]).lower()
            if not all(word in haystack for word in p.get('query', '').lower().split()):
                continue
            entries.append(deepcopy(entry))
        return entries[offset:offset + limit]

    def add(self, actor, entry, resident=False):
        view = self.views[actor]
        if entry['status'] == 'verified' and (entry['id'] in view['loaded'] or len(view['loaded']) < 12):
            view['loaded'][entry['id']] = entry
            if resident:
                view['resident'].add(entry['id'])

    def bound(self, e):
        actor = e['actor']
        state = self.r.state(actor)
        self.views[actor] = dict(loaded={}, resident=set(), used=set())
        selectors = [dict(kind='common', id='*'), dict(kind='node', id=actor)]
        if state['role']:
            selectors.append(dict(kind='role', id=state['role']))
        selectors += [dict(kind='tool', id=name) for name in state['grant']['framework']] + [dict(kind='toolbox', id=name) for name in state['grant']['expanded'] if name != 'network_management']
        for entry in self.query(dict(selectors=selectors, status='verified', core_only=True, limit=10)):
            self.add(actor, entry, True)
        refs = self.r.backend.agents[actor].get('experienceRefs', self.r.config.get('rootExperienceRefs', []) if actor == 'root' else [])
        if refs:
            for entry in self.query(dict(ids=refs, status='verified', limit=10)):
                self.add(actor, entry, True)

    def prepare(self, e):
        actor = e['actor']
        for entry in self.views[actor]['loaded'].values():
            self.r.load(actor, 'experience:' + entry['id'], '经验只作参考；待审核不代表可靠，权限不变。\n[' + entry['id'] + '; ' + entry['version'] + '] ' + entry['trigger'] + '：' + entry['advice'])

    def use(self, e):
        actor, tool = e['actor'], e['name']
        problem = self.r.plugins.get('toolboxes/problem_handling')
        if not problem or not problem.active(actor):
            return
        view = self.views[actor]
        if tool in view['used']:
            return
        def contains(box):
            return any(t['name'] == tool for t in self.r.boxes[box].get('tools', [])) or any(contains(b) for b in self.r.boxes[box].get('includes', []))
        boxes = [box for box in self.r.state(actor)['grant']['expanded'] if contains(box)]
        for entry in self.query(dict(selectors=[dict(kind='tool', id=tool)] + [dict(kind='toolbox', id=box) for box in boxes], status='verified')):
            self.add(actor, entry)
        refs = [id for box in boxes for id in self.r.boxes[box].get('experience_refs', [])]
        if refs:
            for entry in self.query(dict(ids=refs, status='verified')):
                self.add(actor, entry)
        view['used'].add(tool)

    def transient_clear(self, actor):
        view = self.views[actor]
        view['loaded'] = {id: entry for id, entry in view['loaded'].items() if id in view['resident']}
        view['used'].clear()

    def tool_experience_query(self, actor, p):
        if bool(p.get('kind')) != bool(p.get('id')):
            raise ValueError('kind and id must be supplied together')
        entries = self.query(dict(status=p.get('status', 'all'), query=p.get('query', ''), ids=[p['entry_id']] if p.get('entry_id') else [], exclude_ids=[] if p.get('include_resident') or p.get('entry_id') else list(self.views[actor]['resident']), offset=p.get('offset', 0), limit=p.get('limit', 6), selectors=[dict(kind=p['kind'], id=p['id'])] if p.get('kind') else []))
        for entry in entries:
            self.add(actor, entry)
        self.r.plugins['toolboxes/problem_handling'].queried(actor, entries)
        return dict(entries=entries)

    def tool_experience_submit(self, actor, p):
        problem = self.r.plugins['toolboxes/problem_handling']
        problem.can_submit(actor)
        entry = dict(**validate(p), id=str(uuid4()), status='pending', author=actor, created_at=now())
        entry['core'] = False
        self.store.mutate(lambda db: db['entries'].append(entry))
        problem.submitted(actor, entry['id'])
        return dict(id=entry['id'], status='pending')

    def tool_experience_review(self, actor, p):
        if p['action'] == 'list':
            return dict(entries=self.query(dict(status=p.get('status', 'pending'), offset=p.get('offset', 0), limit=10)))
        def review(db):
            entry = next((e for e in db['entries'] if e['id'] == p['id']), None)
            if entry is None:
                raise ValueError('Experience not found')
            action = p['action']
            if action in ('publish', 'reject', 'merge') and entry['status'] != 'pending':
                raise ValueError('Only pending experience can be reviewed')
            if action in ('set_core', 'retire') and entry['status'] != 'verified':
                raise ValueError('Only verified experience can be changed')
            if p.get('changes'):
                if action != 'publish':
                    raise ValueError('changes only apply to publishing')
                entry.update(validate({**entry, **p['changes']}))
            if action == 'merge':
                target = next((e for e in db['entries'] if e['id'] == p.get('merge_into') and e['status'] == 'verified'), None)
                if not target:
                    raise ValueError('Merge target must be verified')
                entry['merged_into'] = target['id']
            if action == 'set_core':
                if type(p.get('core')) is not bool:
                    raise ValueError('core must be boolean')
                entry['core'] = p['core']
            else:
                entry['status'] = dict(publish='verified', reject='rejected', retire='retired', merge='merged')[action]
            entry.update(reviewer=actor, reviewed_at=now(), promotion_candidate=entry['status'] == 'verified' and not entry['core'] and entry.get('success_count', 0) >= 5)
            db['reviews'].append(dict(id=entry['id'], action=action, actor=actor, time=entry['reviewed_at'], entry=deepcopy(entry)))
            return dict(id=entry['id'], status=entry['status'])
        return self.store.mutate(review)
