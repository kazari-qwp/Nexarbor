"""Four input surfaces, isolated by host-owned source, independent of any executor."""
from copy import deepcopy
from hashlib import sha256
from threading import RLock
import json

FIELDS={'system_prompt','context','inputs','tail'}

def identifier(value):
    if not isinstance(value,str) or not value:raise ValueError('Input IDs and sources must be nonempty strings')
    return value

def text(value):
    if isinstance(value,dict) and set(value)=={'file'}:
        from pathlib import Path
        path=Path(value['file'])
        if not path.is_absolute():raise ValueError('Document input requires an absolute path')
        value=path.read_text(encoding='utf-8-sig')
    if not isinstance(value,str):raise ValueError('Input content must be text or an absolute file reference')
    return value

def digest(value):return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

class AgentInputs:
    def __init__(self,state=None):
        self.lock=RLock();self.sources={}
        if state is not None:
            if not isinstance(state,dict):raise ValueError('Invalid Agent input state')
            for source,value in state.items():
                self.update(source,{k:v for k,v in value.items() if k!='inputs'})
                for entry in value.get('inputs',[]):
                    status=entry.get('status')
                    if status not in ('pending','delivered'):raise ValueError('Invalid input delivery state')
                    event={k:v for k,v in entry.items() if k!='status'}
                    self.update(source,{'inputs':[event]})
                    self.sources[source]['inputs'][-1]['status']=status
    def snapshot(self):
        with self.lock:return deepcopy(self.sources)
    def update(self,source,patch):
        identifier(source)
        if not isinstance(patch,dict) or set(patch)-FIELDS:raise ValueError('Unknown Agent input field')
        with self.lock:
            value=deepcopy(self.sources.get(source,dict(system_prompt='',context=[],inputs=[],tail=[])))
            if 'system_prompt' in patch:value['system_prompt']=text(patch['system_prompt'])
            if 'tail' in patch:
                if not isinstance(patch['tail'],list):raise ValueError('tail must be a text list')
                value['tail']=[text(t) for t in patch['tail']]
            if 'context' in patch:
                if not isinstance(patch['context'],list):raise ValueError('context must be a document list')
                docs=[];seen=set()
                for doc in patch['context']:
                    if not isinstance(doc,dict) or set(doc)!={'id','text'}:raise ValueError('Documents require id and text')
                    key=identifier(doc['id']);body=text(doc['text'])
                    if key in seen:raise ValueError('Duplicate document ID')
                    seen.add(key);docs.append(dict(id=key,text=body))
                value['context']=docs
            if 'inputs' in patch:
                if not isinstance(patch['inputs'],list):raise ValueError('inputs must be an event list')
                known={e['id']:e for e in value['inputs']}
                for event in patch['inputs']:
                    if not isinstance(event,dict) or set(event)-{'id','text','delivery'} or not {'id','text'}<=set(event):raise ValueError('Events require id/text and optional delivery')
                    entry=dict(id=identifier(event['id']),text=text(event['text']),delivery=event.get('delivery','followup'))
                    if entry['delivery'] not in ('followup','steer'):raise ValueError('Invalid input delivery')
                    old=known.get(entry['id'])
                    if old and any(old[k]!=v for k,v in entry.items()):raise ValueError('An event ID cannot be reused for different content')
                    if not old:
                        entry['status']='pending';value['inputs'].append(entry);known[entry['id']]=entry
            self.sources[source]=value
            return deepcopy(value)
    def acknowledge(self,source,event_id):
        with self.lock:
            event=next(e for e in self.sources[source]['inputs'] if e['id']==event_id)
            event['status']='delivered'
    def pending(self):
        with self.lock:return [(s,deepcopy(e)) for s,v in sorted(self.sources.items()) for e in v['inputs'] if e['status']=='pending']
    def tail(self):
        with self.lock:return [t for _,v in sorted(self.sources.items()) for t in v['tail']]
