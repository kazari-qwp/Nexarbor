"""Conditional instruction documents using native history markers, independent of signals."""
import json
from hashlib import sha256
from threading import RLock
from datanet.core.application import Component
from datanet.core.metadata import lookup


def digest(value):return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def matches(when,metadata):
    for key,expected in when.items():
        try:actual=lookup(metadata,key)
        except (KeyError,IndexError):return False
        if not (actual in expected if isinstance(expected,list) else actual==expected):return False
    return True


class Plugin(Component):
    def install(self):
        self.sources={};self.locks={}
        self.on('agent/pre-step',lambda e:self.match(e['actor']) if e['actor'] in self.sources else None)

    def bind(self,actor,*,scope,documents):
        if not isinstance(scope,str) or not scope or not callable(documents):raise ValueError('Prompt matching needs a scope and host-owned document provider')
        self.sources.setdefault(actor,{})[scope]=documents
        self.locks.setdefault(actor,RLock())

    def ensure(self,actor,document,text):
        if self.r.host('document-present',actor=actor,document=document):return False
        return self.r.load(actor,document,text)

    def match(self,actor):
        if actor not in self.sources:raise ValueError('No prompt document source is bound')
        with self.locks[actor]:
            results=[]
            for scope,provide_documents in self.sources[actor].items():
                metadata=self.r.backend.network.get_metadata(actor)
                if not isinstance(metadata,dict):raise ValueError('Prompt metadata must be an object')
                selected=[];seen=set();loaded=[]
                for doc in provide_documents():
                    if not isinstance(doc['id'],str) or not doc['id'] or doc['id'] in seen:raise ValueError('Invalid or duplicate prompt document ID')
                    seen.add(doc['id']);when=doc.get('when',{})
                    if not isinstance(when,dict):raise ValueError('Prompt condition must be an object')
                    if not matches(when,metadata):continue
                    if doc['delivery'] not in ('instructions','query'):raise ValueError('Invalid prompt delivery')
                    version=digest(dict(text=doc['text'],when=when,delivery=doc['delivery'],name=doc['name']))
                    key='prompt:'+scope+':'+doc['id']+':'+version
                    if doc['delivery']=='instructions':
                        text='[提示文档：'+doc['name']+']\n适用条件：'+json.dumps(when,ensure_ascii=False,sort_keys=True)+'\n仅在上述条件满足时适用。\n'+doc['text'].strip()
                    else:text='[按需知识] '+doc['name']+'：'+doc['id']
                    if self.ensure(actor,key,text):loaded.append(doc['id'])
                    selected.append(dict(id=doc['id'],version=version))
                current=dict(metadata=metadata,documents=selected)
                before=self.r.rpc('prompt_matching_get',actor=actor,scope=scope)
                changed=not before or before['current']!=current
                revision=(before['revision'] if before else 0)+(1 if changed else 0)
                old_ids={d['id'] for d in before['current']['documents']} if before else set()
                removed=sorted(old_ids-{d['id'] for d in selected}) if changed else (before.get('removed',[]) if before else [])
                state=dict(current=current,revision=revision,removed=removed)
                text='[当前元数据：'+scope+']\n以本条最新元数据为准，旧提示仅在其适用条件仍满足时生效；同一文档以最近注入版本为准。\n'+json.dumps(metadata,ensure_ascii=False,sort_keys=True)+'\n生效文档：'+json.dumps([d['id'] for d in selected],ensure_ascii=False)
                if removed:text+='\n已不匹配：'+json.dumps(removed,ensure_ascii=False)
                self.ensure(actor,'prompt-state:'+scope+':'+str(revision)+':'+digest(current),text)
                if changed:self.r.rpc('prompt_matching_put',actor=actor,scope=scope,value=state)
                results.append(dict(scope=scope,loaded=loaded,matched=[d['id'] for d in selected],state_changed=changed))
            return dict(scopes=results)

    def tool_match_prompts(self,actor,p):return self.match(actor)
