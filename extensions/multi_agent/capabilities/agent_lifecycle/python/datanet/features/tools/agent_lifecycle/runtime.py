"""Optional residency policy, driven by native Agent and graph events."""
from threading import RLock, Timer, Event
from hashlib import sha256
from time import monotonic
import json
from datanet.core.application import Component
from datanet.services.tools.agent_lifecycle.services import records, reachable


class Plugin(Component):
    def install(self):
        self.lock = RLock()
        self.settle_lock = RLock()
        self.closed, self.timer = False, None
        self.last_activity = monotonic()
        self.residency_busy = False
        self.residency_done = Event()
        self.residency_done.set()
        self.mounting = {}
        self.idle_seconds = self.r.config.get('networkIdleTimeoutMs', 30 * 60 * 1000) / 1000
        self.on('agent/bound', self.bound)
        self.on('agent/pre-step', self.activity)
        self.on('context/prepare', self.activity)
        self.on('tool/before', self.activity)
        self.on('agent/status', self.status)
        self.on('graph/changed', self.changed)
        self.on('agent/ensure-mounted', self.ensure_event)
        self.on('delegation/settled', self.status)

    def bound(self, e):
        self.last_activity = monotonic()
        self.arm()

    def arm(self, delay=None):
        if self.closed or self.idle_seconds <= 0:
            return
        with self.lock:
            if self.timer:
                self.timer.cancel()
            self.timer = Timer(self.idle_seconds if delay is None else delay, self.tick)
            self.timer.daemon = True
            self.timer.start()

    def activity(self, e):
        self.last_activity = monotonic()
        self.residency_done.wait(30)
        if self.r.backend.lifecycle['sleeping']:
            self.restore_connected()
        self.arm()

    def pinned(self, ids=None):
        ids = set(self.r.states) if ids is None else set(ids)
        jobs = self.r.plugins.get('capabilities/agent_delegation')
        if jobs and jobs.pending_nodes() & ids:
            return True
        discussion = self.r.plugins.get('capabilities/discussion_group')
        if discussion and discussion.busy:
            # A discussion is one scheduled operation, including gaps between members.
            for group_id in discussion.busy:
                group = getattr(self.r.backend, 'groups', {}).get(group_id)
                if group and ids.intersection([group['board'].node_id, *group['board'].members]):
                    return True
        for actor in ids & self.r.states.keys():
            if self.r.state(actor).get('scheduled') or self.r.host('inspect', actor=actor)['status'] != 'idle':
                return True
        messages = self.r.plugins.get('capabilities/agent_messaging')
        if messages:
            for entry in messages.store.data['messages'].values():
                if entry['status'] == 'pending' and not entry.get('delivered', True) and (entry['to'] in ids or entry['from'] in ids):
                    return True
        return False

    def tick(self):
        try:
            if self.closed:
                return
            self.settle()
            remaining = self.idle_seconds - (monotonic() - self.last_activity)
            if remaining > 0:
                self.arm(remaining)
            elif self.pinned():
                self.arm(min(30, self.idle_seconds))
            else:
                self.unload(set(self.r.backend.network.nodes) - {'root'}, sleeping=True)
        except Exception as error:
            self.r.errors.append(dict(component=self.id, error=str(error)))
            self.arm(min(30, self.idle_seconds))

    def status(self, e):
        if e.get('status', 'idle') == 'idle':
            self.last_activity = monotonic()
            self.arm()
            # Native status callbacks must return before disposing their Agent.
            timer = Timer(.05, self.settle)
            timer.daemon = True
            timer.start()

    def changed(self, e):
        self.last_activity = monotonic()
        self.residency_done.wait(30)
        self.restore_connected()
        self.settle()

    def settle(self):
        if not self.settle_lock.acquire(blocking=False):
            return
        try:
            self.settle_pending()
        finally:
            self.settle_lock.release()

    def settle_pending(self):
        if self.closed or self.residency_busy:
            return
        for operation in list(self.r.backend.lifecycle['deferred']):
            if self.pinned(operation['ids']):
                continue
            rows = records(self.r.backend)
            ids = set(operation['ids']) - reachable(rows)
            if ids:
                self.r.rpc('lifecycle_archive', network_id=operation['network_id'], ids=sorted(ids), entry=operation['entry'], owner=operation['owner'], choice=operation['choice'])
            self.unload(ids)
            if operation['choice'] == 3 and ids:
                self.r.rpc('lifecycle_decompose', ids=sorted(ids))
            pending = list(self.r.backend.lifecycle['deferred'])
            if operation in pending:
                pending.remove(operation)
                self.r.rpc('lifecycle_update', deferred=pending)

    def unload(self, ids, sleeping=False):
        if not ids and not sleeping:
            return
        with self.lock:
            if self.residency_busy:
                return
            self.residency_busy = True
            self.residency_done.clear()
        generation = self.last_activity
        try:
            self.r.rpc('save')
            def depth(actor):
                seen = set()
                while actor and actor not in seen:
                    seen.add(actor)
                    actor = self.r.backend.agents.get(actor, {}).get('native_parent_id')
                return len(seen)
            for actor in sorted(set(ids) & self.r.states.keys(), key=depth, reverse=True):
                self.r.emit('agent/unbinding', actor=actor)
                self.r.host('dispose-agent', actor=actor)
                self.r.states.pop(actor, None)
            self.r.rpc('lifecycle_park', ids=sorted(ids), sleeping=sleeping)
        finally:
            self.residency_busy = False
            self.residency_done.set()
        if sleeping and self.last_activity != generation:
            self.restore_connected()

    def restore_connected(self):
        result = self.r.rpc('lifecycle_wake')
        for actor in result['loaded']:
            self.mount(actor)

    def mount(self, actor):
        if actor == 'root' or actor in self.r.states or actor not in self.r.backend.agents:
            return
        saved = self.r.backend.agents[actor]
        if actor in self.r.backend.lifecycle['pool']:
            return
        with self.lock:
            existing = self.mounting.get(actor)
            if existing is None:
                ready = self.mounting[actor] = Event()
        if existing is not None:
            if not existing.wait(60):
                raise TimeoutError('Agent mount is still pending')
            if actor not in self.r.states:
                raise RuntimeError('Concurrent Agent mount failed')
            return
        management = self.r.plugins['capabilities/tools_network_management']
        try:
            management.create(actor, saved['prompt'], saved.get('manager_id') if saved.get('manager_id') in self.r.states else 'root', saved['maxStrength'], saved['toolboxes'], saved.get('role'), saved)
        finally:
            with self.lock:
                self.mounting.pop(actor, None)
                ready.set()

    def ensure_event(self, e):
        self.residency_done.wait(30)
        actor = e['target']
        if actor in self.r.backend.lifecycle['pool']:
            raise ValueError('Agent is in the reuse pool; create an Agent node to acquire it')
        if actor not in self.r.backend.network.nodes:
            result = self.r.rpc('lifecycle_wake', target=actor)
            for id in result['loaded']:
                self.mount(id)
        self.mount(actor)

    def initial(self):
        rows = records(self.r.backend)
        disconnected = set(rows) - reachable(rows)
        self.unload(disconnected)

    def claim(self, target, spec):
        key = sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return key, self.r.rpc('lifecycle_claim', target=target, key=key)

    def close(self):
        self.closed = True
        if self.timer:
            self.timer.cancel()
