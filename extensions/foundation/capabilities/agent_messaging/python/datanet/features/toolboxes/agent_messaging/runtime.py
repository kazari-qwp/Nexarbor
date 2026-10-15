from threading import RLock, Timer
from uuid import uuid4
import json, time
from datanet.core.application import Component
from datanet.core.state_store import JsonStore

SEND_DESCRIPTION = '向自己的管理者或直接被管理的 Agent 发信；运行中插话，空闲时唤醒。'
REPLY_DESCRIPTION = '仅用来回复此条消息，调用一次后失效'


class Plugin(Component):
    def install(self):
        self.store = JsonStore(self.r.directory / 'communications/messages.json', dict(version=1, messages={}))
        self.lock, self.timers, self.closed = RLock(), {}, False
        self.ttl = self.r.config.get('messageReplyTimeoutMs', 30 * 60 * 1000)
        if self.ttl <= 0:
            raise ValueError('Reply lifetime must be positive')
        self.on('agent/bound', self.bound)
        self.on('context/tail', self.tail)
        self.on('capabilities/changed', lambda e: self.refresh(e['actor']))
        self.on('message/discarded', self.discarded)
        self.on('agent/pre-step', self.read_delivered)
        self.on('context/admitted', self.read_delivered)
        self.on('tool/available', self.available)
        for entry in self.store.data['messages'].values():
            entry.setdefault('message_type', 'reply' if entry.get('reply_to') else 'work_order')
            entry.setdefault('read_at', None)
            if entry['status'] == 'pending' and entry['expires_at'] <= time.time() * 1000:
                entry['status'] = 'expired'
        self.store.save()

    def can_send(self, actor):
        return 'datanet_send_message' in self.r.state(actor)['grant']['framework']

    def available(self, e):
        if e['name'] == 'datanet_contacts_channel' and not self.can_send(e['actor']):
            e['allowed'] = False

    def contacts(self, actor):
        binding = self.r.backend.agents.get(actor, {})
        return list(dict.fromkeys(id for id in [binding.get('manager_id'), *binding.get('managed_ids', [])] if id and id != actor and id in self.r.backend.agents))

    def pending(self, actor):
        return [entry for entry in self.store.data['messages'].values() if entry['to'] == actor and entry['status'] == 'pending' and entry['expires_at'] > time.time() * 1000]

    def bound(self, e):
        actor = e['actor']
        self.refresh(actor)
        history = self.r.host('inbox-snapshot', actor=actor)
        seen = {m['id'] for m in history}
        for entry in self.pending(actor):
            if entry.get('message') and entry['inbox_id'] not in seen:
                self.r.host('steer', actor=actor, message=entry['message'])

    def tail(self, e):
        pending = self.pending(e['actor'])
        if any(p['message_type'] == 'work_order' for p in pending):
            e['texts'].append('存在待处理工单。')
        if any(p['message_type'] == 'reply' and p['read_at'] is None for p in pending):
            e['texts'].append('存在未读回复。')

    def read_delivered(self, e):
        seen = set(e.get('message_ids', [])) | {m['id'] for m in e.get('messages', []) if 'id' in m}
        if not seen:
            return
        with self.lock:
            changed = False
            for entry in self.pending(e['actor']):
                if entry['read_at'] is None and entry.get('inbox_id') in seen:
                    entry['read_at'] = int(time.time() * 1000)
                    changed = True
            if changed:
                self.store.save()


    def refresh(self, actor):
        dynamic = self.r.state(actor)['dynamic']
        available = {entry['reply_tool']: entry for entry in self.pending(actor)}
        dynamic['datanet_pending_messages'] = dict(owner=self.id, **self.r.tools['datanet_pending_messages'])
        for name in list(dynamic):
            if dynamic[name]['owner'] == self.id and name not in available and name not in ('datanet_send_message', 'datanet_pending_messages'):
                del dynamic[name]
        parameters = dict(type='object', properties={'content': {'type': 'string', 'minLength': 1}}, required=['content'], additionalProperties=False)
        if self.can_send(actor):
            dynamic['datanet_send_message'] = dict(owner=self.id, name='datanet_send_message', description=SEND_DESCRIPTION, parameters={**parameters, 'properties': {**parameters['properties'], 'target': {'type': 'string', 'minLength': 1}, 'message_type': {'type': 'string', 'enum': ['work_order', 'reply'], 'default': 'work_order', 'description': 'work_order 需要答复；reply 可不回复。'}}, 'required': ['target', 'content']})
        else:
            dynamic.pop('datanet_send_message', None)
        for name, entry in available.items():
            dynamic[name] = dict(owner=self.id, name=name, description=REPLY_DESCRIPTION, parameters=parameters)
            if entry['id'] not in self.timers:
                timer = Timer(max(.001, (entry['expires_at'] - time.time() * 1000) / 1000), self.expire, args=(entry['id'],))
                timer.daemon = True
                self.timers[entry['id']] = timer
                timer.start()
        self.r.refresh(actor)

    def expire(self, id):
        with self.lock:
            entry = self.store.data['messages'].get(id)
            if not entry or entry['status'] != 'pending' or self.closed:
                return
            entry['status'] = 'expired'
            self.store.save()
            self.timers.pop(id, None)
        if entry['to'] in self.r.states:
            self.refresh(entry['to'])

    def discarded(self, e):
        with self.lock:
            for entry in self.pending(e['actor']):
                if entry['inbox_id'] == e['message_id']:
                    entry['status'] = 'discarded'
            self.store.save()
        self.refresh(e['actor'])

    def invoke(self, actor, name, args):
        added = self.r.load(actor, 'tool:datanet_messages', self.r.resource(self.id, 'guides/datanet_messages/AGENTS.md'))
        with self.lock:
            if name == 'datanet_contacts_channel':
                return dict(contacts=self.contacts(actor), instructions_added=added)
            if name == 'datanet_pending_messages':
                if args.get('action', 'read') == 'close':
                    entry = next((p for p in self.pending(actor) if p['id'] == args.get('message_id')), None)
                    if entry is None:
                        raise ValueError('message_id 须为自己的有效消息 ID')
                    entry['status'] = 'closed'
                    self.store.save()
                    self.refresh(actor)
                    return dict(status='closed', message_id=entry['id'])
                result = []
                for p in self.pending(actor):
                    if p['read_at'] is None:
                        p['read_at'] = int(time.time() * 1000)
                    result.append(dict(message_id=p['id'], **{'from': p['from']}, message_type=p['message_type'], content=p['content'], reply_tool=p['reply_tool'], expires_at=p['expires_at'], read=p['read_at'] is not None, **({'notice': '此为回复，可以不回。'} if p['message_type'] == 'reply' else {})))
                self.store.save()
                return dict(messages=result)
            if name == 'datanet_send_message':
                if not self.can_send(actor):
                    raise PermissionError('[DATANET_TOOL_PERMISSION_DENIED] datanet_send_message 当前已停用。')
                if args['target'] not in self.contacts(actor):
                    raise PermissionError('Target is outside Agent management contacts')
                return self.deliver(actor, args['target'], args['content'], message_type=args.get('message_type', 'work_order'))
            original = next((e for e in self.store.data['messages'].values() if e['reply_tool'] == name), None)
            if not original or original['to'] != actor:
                raise PermissionError('Reply belongs to another Agent')
            if original['status'] != 'pending' or original['expires_at'] <= time.time() * 1000:
                raise PermissionError('[DATANET_TOOL_PERMISSION_DENIED] ' + name + ' 当前已停用。')
            return self.deliver(actor, original['from'], args['content'], original)

    def deliver(self, sender, receiver, content, original=None, message_type='work_order'):
        if original:
            message_type = 'reply'
        if message_type not in ('work_order', 'reply'):
            raise ValueError('message_type 须为 work_order 或 reply')
        if self.closed:
            raise RuntimeError('Message router is closed')
        if not isinstance(content, str) or not content.strip():
            raise ValueError('Message content is required')
        self.r.emit('agent/ensure-mounted', target=receiver)
        if sender not in self.r.states or receiver not in self.r.states:
            raise ValueError('Target Agent is not mounted; message was not accepted')
        self.r.host('inspect', actor=receiver)
        id = str(uuid4())
        entry = dict(id=id, to=receiver, content=content, message_type=message_type, read_at=None, status='pending', created_at=int(time.time() * 1000), expires_at=int(time.time() * 1000) + self.ttl, reply_tool='datanet_reply_' + id.replace('-', ''), communication_id=original['communication_id'] if original else id)
        entry['from'] = sender
        if original:
            entry['reply_to'] = original['id']
        payload = dict(type=message_type, **{'from': sender}, communication_id=entry['communication_id'], message_id=id, reply_tool=entry['reply_tool'], content=content)
        if original:
            payload['reply_to'] = original['id']
        message = self.r.host('make-message', **{'from': sender}, text=('此为回复，可以不回。\n' if message_type == 'reply' else '') + json.dumps(payload, ensure_ascii=False))
        entry.update(message=message, inbox_id=message['id'])
        self.store.data['messages'][id] = entry
        if original:
            original['status'] = 'replied'
        try:
            self.store.save()
            self.refresh(receiver)
            self.refresh(sender)
            self.r.host('steer', actor=receiver, message=message)
        except Exception:
            self.store.data['messages'].pop(id)
            if original:
                original['status'] = 'pending'
            self.store.save()
            self.refresh(receiver)
            self.refresh(sender)
            raise
        return dict(status='accepted', communication_id=entry['communication_id'], message_id=id, inbox_message_id=entry['inbox_id'])

    def close(self):
        self.closed = True
        for timer in self.timers.values():
            timer.cancel()
