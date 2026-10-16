"""Explicit context manifests over native input surfaces; no domain or signal dependency."""
from pathlib import Path
from threading import RLock
import json
from datanet.core.application import Component,checked
from datanet.core.agent_inputs import digest
from datanet.core.metadata import lookup
from .services import state

def matches(when,metadata):
    for key,expected in when.items():
        try:actual=lookup(metadata,key)
        except (KeyError,IndexError,TypeError):return False
        if not (actual in expected if isinstance(expected,list) else actual==expected):return False
    return True

class Plugin(Component):
    def install(self):
        self.locks={}
        self.on('agent/pre-step',lambda e:self.assemble(e['actor']))
        self.on('context/prepare',lambda e:self.assemble(e['actor']))
    def configure(self,node_id,sources,document_roots=()):return self.r.rpc('context_assembly_configure',actor='root',node_id=node_id,sources=sources,document_roots=list(document_roots))
    def bind(self,actor,node_id):return self.r.rpc('context_assembly_bind',actor='root',target=actor,node_id=node_id)
    def allowed(self,owner,target,strength):
        return any(e.target_node_id==target and e.allows(origin_node_id=owner,source_node_id=owner,strength=strength) for e in self.r.backend.network.nodes[owner].read_interfaces)
    def read(self,node_id,spec,config,strength):
        source=spec['source'];kind=source['type']
        if kind=='text':return source['text']
        if kind=='resource':
            if source['component'] not in self.r.enabled:raise PermissionError('Context resource component is disabled')
            return self.r.resource(source['component'],source['file'])
        if kind=='file':
            path=Path(source['path']).resolve()
            if not any(path.is_relative_to(Path(root)) for root in config['document_roots']):raise PermissionError('Document moved outside granted roots')
            return path.read_text(encoding='utf-8-sig')
        target=source['target']
        if not self.allowed(node_id,target,strength):raise PermissionError('Assembly node has no direct read grant: '+target)
        if spec.get('reference_only'):return '[按需知识] '+spec.get('name',spec['id'])+'：'+target
        from datanet.core.component_registry import node_enabled
        node=self.r.backend.network.nodes[target]
        if not node_enabled(node):raise PermissionError('Context node component is disabled')
        result=node.read(dict(method='key',key=source.get('key','content')))
        checked(result)
        if result.status!='ok' or len(result.items)!=1 or not isinstance(result.items[0].get('content'),str):raise ValueError('Context node must return one text document')
        return result.items[0]['content']
    def assemble(self,actor):
        with self.locks.setdefault(actor,RLock()):
            b=self.r.backend;reports=[];metadata=b.network.get_metadata(actor);strength=self.r.state(actor)['strength']
            for node_id in state(b)['bindings'].get(actor,[]):
                owner='context-assembly:'+node_id
                if not self.allowed(actor,node_id,strength):
                    self.r.update_inputs(actor,owner,system_prompt='',context=[],tail=[])
                    reports.append(dict(node_id=node_id,matched=[],loaded=[],revoked=True));continue
                config=state(b)['nodes'][node_id];system=[];context=[];tail=[];events=[];selected=[]
                for spec in sorted(config['sources'],key=lambda s:(s.get('order',0),s['id'])):
                    if not matches(spec.get('when',{}),metadata):continue
                    body=self.read(node_id,spec,config,strength);kind=spec['kind']
                    if kind in ('system_prompt','context'):selected.append(dict(id=spec['id'],version=digest([body,spec])))
                    if kind=='system_prompt':system.append(body.strip())
                    elif kind=='tail':tail.append(body)
                    elif kind=='inputs':events.append(dict(id=spec['event_id'],text=body,delivery=spec.get('delivery','followup')))
                    else:
                        text=body if spec.get('reference_only') else '[提示文档：'+spec.get('name',spec['id'])+']\n适用条件：'+json.dumps(spec.get('when',{}),ensure_ascii=False,sort_keys=True)+'\n仅在上述条件满足时适用。\n'+body.strip()
                        context.append(dict(id=spec['id'],text=text))
                # Applicability is a small latest snapshot; loading is governed by native history markers.
                current=dict(metadata=metadata,documents=selected);before=self.r.rpc('context_assembly_get',target=actor,node_id=node_id)
                changed=not before or before['current']!=current;revision=(before['revision'] if before else 0)+(1 if changed else 0)
                old_ids={d['id'] for d in before['current']['documents']} if before else set()
                removed=sorted(old_ids-{d['id'] for d in selected}) if changed else (before.get('removed',[]) if before else [])
                snapshot='[当前元数据：'+node_id+']\n以本条最新元数据为准，旧提示仅在其适用条件仍满足时生效；同一文档以最近注入版本为准。\n'+json.dumps(metadata,ensure_ascii=False,sort_keys=True)+'\n生效来源：'+json.dumps([d['id'] for d in selected],ensure_ascii=False)
                if removed:snapshot+='\n已不匹配：'+json.dumps(removed,ensure_ascii=False)
                context.append(dict(id='state:'+str(revision)+':'+digest(current),text=snapshot))
                result=self.r.update_inputs(actor,owner,system_prompt='\n\n'.join(system),context=context,inputs=events,tail=tail)
                loaded=[d['id'] for d in result.get('_loaded',[]) if d['source']==owner and not d['id'].startswith('state:')]
                if changed:self.r.rpc('context_assembly_put',actor='root',target=actor,node_id=node_id,value=dict(current=current,revision=revision,removed=removed))
                reports.append(dict(node_id=node_id,matched=[d['id'] for d in selected],loaded=loaded,state_changed=changed))
            return dict(sources=reports)
    def close(self):
        for actor,nodes in state(self.r.backend)['bindings'].items():
            if actor not in self.r.states:continue
            for node_id in nodes:self.r.update_inputs(actor,'context-assembly:'+node_id,system_prompt='',context=[],tail=[])
