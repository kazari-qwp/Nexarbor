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
        self.on('capabilities/changed', lambda e: self.refresh(e['actor']))
        self.on('message/discarded', self.discarded)
        for entry in self.store.data['messages'].values():
            if entry['status'] == 'pending' and entry['expires_at'] <= time.time() * 1000:
                entry['status'] = 'expired'
        self.store.save()

    def can_send(self, actor):
        return 'datanet_send_message' in self.r.state(actor)['grant']['framework']

    def contacts(self, actor):
        binding = self.r.backend.agents.get(actor, {})
        return list(dict.fromkeys(id for id in [binding.get('manager_id'), *binding.get('managed_ids', [])] if id and id != actor and id in self.r.backend.agents))

    def pending(self, actor):
        return [entry for entry in self.store.data['messages'].values() if entry['to'] == actor and entry['status'] == 'pending' and entry['expires_at'] > time.time() * 1000]

    def bound(self, e):
        actor = e['actor']
        self.section(actor, 'datanet:messages', lambda: self.render(actor), 89.1)
        self.refresh(actor)
        history = self.r.host('inbox-snapshot', actor=actor)
        seen = {m['id'] for m in history}
        for entry in self.pending(actor):
            if entry.get('message') and entry['inbox_id'] not in seen:
                self.r.host('steer', actor=actor, message=entry['message'])

    def render(self, actor):
        return ('可主动联系：' + json.dumps(self.contacts(actor), ensure_ascii=False) if self.can_send(actor) else '') + ('\n待回复消息：' + json.dumps([dict(message_id=e['id'], **{'from': e['from']}, reply_tool=e['reply_tool'], expires_at=e['expires_at']) for e in self.pending(actor)], ensure_ascii=False) if self.pending(actor) else '')

    def refresh(self, actor):
        dynamic = self.r.state(actor)['dynamic']
        available = {entry['reply_tool']: entry for entry in self.pending(actor)}
        for name in list(dynamic):
            if dynamic[name]['owner'] == self.id and name not in available and name != 'datanet_send_message':
                del dynamic[name]
        parameters = dict(type='object', properties={'content': {'type': 'string', 'minLength': 1}}, required=['content'], additionalProperties=False)
        if self.can_send(actor):
            dynamic['datanet_send_message'] = dict(owner=self.id, name='datanet_send_message', description=SEND_DESCRIPTION, parameters={**parameters, 'properties': {**parameters['properties'], 'target': {'type': 'string', 'minLength': 1}}, 'required': ['target', 'content']})
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
        self.r.load(actor, 'tool:datanet_messages', self.r.resource(self.id, 'guides/datanet_messages/AGENTS.md'))
        with self.lock:
            if name == 'datanet_send_message':
                if not self.can_send(actor):
                    raise PermissionError('[DATANET_TOOL_PERMISSION_DENIED] datanet_send_message 当前已停用。')
                if args['target'] not in self.contacts(actor):
                    raise PermissionError('Target is outside Agent management contacts')
                return self.deliver(actor, args['target'], args['content'])
            original = next((e for e in self.store.data['messages'].values() if e['reply_tool'] == name), None)
            if not original or original['to'] != actor:
                raise PermissionError('Reply belongs to another Agent')
            if original['status'] != 'pending' or original['expires_at'] <= time.time() * 1000:
                raise PermissionError('[DATANET_TOOL_PERMISSION_DENIED] ' + name + ' 当前已停用。')
            return self.deliver(actor, original['from'], args['content'], original)

    def deliver(self, sender, receiver, content, original=None):
        if self.closed:
            raise RuntimeError('Message router is closed')
        if not isinstance(content, str) or not content.strip():
            raise ValueError('Message content is required')
        if sender not in self.r.states or receiver not in self.r.states:
            raise ValueError('Target Agent is not mounted; message was not accepted')
        self.r.host('inspect', actor=receiver)
        id = str(uuid4())
        entry = dict(id=id, to=receiver, content=content, status='pending', created_at=int(time.time() * 1000), expires_at=int(time.time() * 1000) + self.ttl, reply_tool='datanet_reply_' + id.replace('-', ''), communication_id=original['communication_id'] if original else id)
        entry['from'] = sender
        if original:
            entry['reply_to'] = original['id']
        payload = dict(type='reply' if original else 'message', **{'from': sender}, communication_id=entry['communication_id'], message_id=id, reply_tool=entry['reply_tool'], content=content)
        if original:
            payload['reply_to'] = original['id']
        message = self.r.host('make-message', **{'from': sender}, text=json.dumps(payload, ensure_ascii=False))
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
