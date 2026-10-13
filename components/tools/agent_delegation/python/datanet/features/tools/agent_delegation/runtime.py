"""Persistent asynchronous FIFO delegations; business execution stays in Harness."""
from threading import RLock, Event, Thread, current_thread
from uuid import uuid4
import json
import time
from datanet.core.application import Component
from datanet.core.state_store import JsonStore


WAIT_DESCRIPTION = '等待或查看自己发起的委托，按委托 ID 返回执行结果。'


class Plugin(Component):
    def install(self):
        self.lock, self.workers, self.events, self.waiters = RLock(), {}, {}, {}
        self.closed = False
        self.recovered = False
        self.store = JsonStore(self.r.directory / 'delegations/queue.json', dict(version=1, jobs={}))
        for job in self.jobs.values():
            if job['status'] == 'running':
                job.update(status='interrupted', result=dict(status='interrupted', error='客户端关闭时委托尚未完成，请检查已保存进度。'))
        self.store.save()
        self.on('agent/bound', self.bound)
        self.on('agent/pre-step', self.ready)

    @property
    def jobs(self):
        return self.store.data['jobs']

    def bound(self, e):
        actor = e['actor']
        if any(job['caller'] == actor for job in self.jobs.values()):
            self.unlock(actor)
    def ready(self, e):
        if e['actor'] != 'root' or self.recovered:
            return
        self.recovered = True
        # Creation only assembles contexts. Start recovered jobs after the root
        # enters its native loop, when every creation callback has finished.
        Thread(target=self.recover, daemon=True).start()

    def recover(self):
        for target in dict.fromkeys(job['target'] for job in self.jobs.values() if job['status'] == 'queued'):
            self.start_worker(target)
        for job in list(self.jobs.values()):
            if job['status'] in ('completed', 'failed', 'blocked', 'interrupted') and not job.get('delivered'):
                self.deliver(job)

    def unlock(self, actor):
        self.r.state(actor)['dynamic']['datanet_wait_agent'] = dict(owner=self.id, name='datanet_wait_agent', description=WAIT_DESCRIPTION, parameters=dict(type='object', properties={'delegation_id': {'type': 'string'}, 'wait': {'type': 'boolean', 'default': True}, 'timeout_ms': {'type': 'integer', 'minimum': 0, 'maximum': 540000}}, required=['delegation_id'], additionalProperties=False))
        self.r.refresh(actor)

    def submit(self, caller, target, task):
        if not isinstance(task, str) or not task.strip():
            raise ValueError('Task required')
        reports = self.r.plugins.get('tools/reports')
        reference = reports.delegate(caller, target, task, activate=False) if reports else None
        id = reference['delegation_id'] if reference else str(uuid4())
        with self.lock:
            job = dict(id=id, caller=caller, target=target, task=task, status='queued', created_at=time.time(), report_reference=reference, delivered=False)
            self.jobs[id] = job
            self.events[id] = Event()
            self.store.save()
            position = sum(j['target'] == target and j['status'] in ('queued', 'running') for j in self.jobs.values())
        self.unlock(caller)
        self.r.load(caller, 'tool:datanet_delegation', self.r.resource(self.id, 'AGENTS.md'))
        self.start_worker(target)
        return dict(status='accepted', delegation_id=id, target=target, queue_position=position, report_reference=reference)

    def start_worker(self, target):
        with self.lock:
            if self.closed or target in self.workers:
                return
            worker = Thread(target=self.run_queue, args=(target,), name='datanet-delegation', daemon=True)
            self.workers[target] = worker
            worker.start()

    def run_queue(self, target):
        try:
            while not self.closed:
                with self.lock:
                    job = next((job for job in self.jobs.values() if job['target'] == target and job['status'] == 'queued'), None)
                    if job is None:
                        break
                try:
                    self.r.emit('agent/ensure-mounted', target=target)
                    # send_message may already have started a native loop.
                    while self.r.host('inspect', actor=target)['status'] != 'idle':
                        if self.closed:
                            return
                        time.sleep(.05)
                    with self.lock:
                        job.update(status='running', started_at=time.time())
                        self.store.save()
                    result = self.r.plugins['tools/network_management'].execute(job['caller'], target, job['task'], reference=job['report_reference'], asynchronous=True)
                    status = 'blocked' if result['status'] == 'blocked' else 'completed'
                except Exception as error:
                    status, result = 'failed', dict(status='failed', error=str(error))
                    reports = self.r.plugins.get('tools/reports')
                    if reports and job['report_reference']:
                        reports.end(job['report_reference'], 'failed', str(error))
                with self.lock:
                    job.update(status=status, result=result, finished_at=time.time())
                    self.store.save()
                    self.events.setdefault(job['id'], Event()).set()
                self.deliver(job)
                self.r.emit('delegation/settled', actor=target, delegation_id=job['id'])
        finally:
            with self.lock:
                self.workers.pop(target, None)
                again = not self.closed and any(job['target'] == target and job['status'] == 'queued' for job in self.jobs.values())
            if again:
                self.start_worker(target)

    def deliver(self, job):
        with self.lock:
            if job.get('delivered') or self.closed:
                return
            waiting = self.waiters.get(job['id'], 0)
        try:
            if not waiting:
                self.r.emit('agent/ensure-mounted', target=job['caller'])
                if job['caller'] not in self.r.states:
                    return
                payload = dict(type='delegation_result', delegation_id=job['id'], target=job['target'], status=job['status'], result=job['result'], report_reference=job['report_reference'])
                self.r.host('steer', actor=job['caller'], text=json.dumps(payload, ensure_ascii=False))
            with self.lock:
                job['delivered'] = True
                self.store.save()
        except Exception as error:
            self.r.errors.append(dict(component=self.id, delegation_id=job['id'], delivery_error=str(error)))

    def tool_datanet_wait_agent(self, actor, p):
        id = p['delegation_id']
        with self.lock:
            job = self.jobs.get(id)
            if not job or job['caller'] != actor:
                raise PermissionError('Delegation is absent or belongs to another Agent')
            event = self.events.setdefault(id, Event())
            pending = job['status'] in ('queued', 'running')
            if pending and p.get('wait', True):
                self.waiters[id] = self.waiters.get(id, 0) + 1
        if pending and p.get('wait', True):
            try:
                event.wait(p.get('timeout_ms', 540000) / 1000)
            finally:
                with self.lock:
                    self.waiters[id] -= 1
                    if job['status'] not in ('queued', 'running'):
                        job['delivered'] = True
                        self.store.save()
        with self.lock:
            return dict(delegation_id=id, target=job['target'], status=job['status'], result=job.get('result'), report_reference=job['report_reference'])

    def pending_nodes(self):
        with self.lock:
            return {id for job in self.jobs.values() if job['status'] in ('queued', 'running') or not job.get('delivered') for id in (job['caller'], job['target'])}

    def close(self):
        self.closed = True
        for event in self.events.values():
            event.set()
        for worker in list(self.workers.values()):
            if worker is not current_thread():
                worker.join(timeout=1)
