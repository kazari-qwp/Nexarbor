"""Independent probability events; the caller owns the enclosing action transaction."""
from copy import deepcopy
from hashlib import sha256
from math import isfinite
from uuid import uuid4
from datanet.core.node_modules import NodeModule

class Events(NodeModule):
    def install(self):
        seen=set()
        for e in self.config['events']:
            if not isinstance(e.get('id'),str) or not e['id'] or e['id'] in seen:raise ValueError('Unique event IDs required')
            seen.add(e['id']);p=e.get('probability');limit=e.get('max_occurrences')
            if type(p) not in (int,float) or not isfinite(p) or not 0<=p<=1:raise ValueError('Probability must be between zero and one')
            if limit is not None and (type(limit) is not int or limit<0):raise ValueError('Occurrence cap must be nonnegative or null')
            if not isinstance(e.get('text'),str) or not isinstance(e.get('actions'),list) or not e['actions']:raise ValueError('Event text and actions required')
        self.state.setdefault('seed',uuid4().hex);self.state.setdefault('counts',{});self.state.setdefault('draws',{})
    def draw(self,action_id,action,apply_effects):
        if not isinstance(action_id,str) or not action_id:raise ValueError('Stable successful action ID required')
        if action_id in self.state['draws']:
            record=self.state['draws'][action_id]
            if record['action']!=action:raise ValueError('Action ID reused for a different action')
            return deepcopy(record['events'])
        emitted=[]
        for e in self.config['events']:
            if action not in e['actions']:continue
            count=self.state['counts'].get(e['id'],0);cap=e.get('max_occurrences')
            if cap is not None and count>=cap:continue
            key=self.state['seed']+'\0'+action_id+'\0'+e['id']
            roll=(int.from_bytes(sha256(key.encode()).digest()[:8],'big')>>11)/2**53
            if roll>=e['probability']:continue
            effects=deepcopy(e.get('effects',[]))
            applied=apply_effects(effects) if effects else []
            self.state['counts'][e['id']]=count+1
            emitted.append(dict(text=e['text'],effects=applied))
        self.state['draws'][action_id]=dict(action=action,events=deepcopy(emitted))
        return emitted

def register(s):s.node_module('probability.events',Events)
