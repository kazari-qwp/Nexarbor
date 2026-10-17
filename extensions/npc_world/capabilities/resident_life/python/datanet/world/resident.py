from datanet.world.model import *
from datanet.core.component_registry import resource_directory
import json
from uuid import uuid4
TOOLS=json.loads((resource_directory(__file__).parents[2]/"tools.json").read_text(encoding="utf-8"))

class Resident(ActionModule):
    module_name='world.resident'
    tools=TOOLS
    bind_order=-10
    def apply(self,actor,name,args):
        b=self.backend;a=person(b,actor).state;other=self.state
        if a['place']!=other['place']:raise PermissionError('Not in the same place')
        if name=='talk':
            other['inbox'].append(dict(id=uuid4().hex,actor=actor,content=args['content'],tick=tick(b)))
            other['inbox'][:]=other['inbox'][-100:]
            return dict(delivered=True,recipient=self.node.node_id,notice='交谈不会额外唤醒对方。')
        take(a,args['item'],args['quantity']);add(other,args['item'],args['quantity']);return dict(delivered=True)
    def bind(self,r):
        self.r=r
        if not self.listeners:
            self.listen(r,'capabilities/resident_life','agent/pre-step',self.pre_step)
            self.listen(r,'capabilities/resident_life','node/tool-unavailable',self.unavailable)
    def unavailable(self,e):
        failure=e['failure']
        if failure['target']!=self.node.node_id or failure['tool']!='talk':return
        caller=self.backend.modules.instances.get((failure['actor'],'world.resident'))
        if not caller or caller.state['place']==self.state['place']:return
        seen=caller.state.get('departures',{}).get(self.node.node_id)
        if seen and seen['origin']==caller.state['place']:
            failure['message']=self.state['name']+'好像已经去了「'+seen['name']+'」，已经不在这里了。'
        else:failure['message']=self.state['name']+'已经不在这里了。'

    def pre_step(self,e):
        if e['actor']!=self.node.node_id:return
        budget=instance(self.backend,self.node.node_id,'action.budget').status(period=tick(self.backend))
        text='[小镇] 地点：'+self.state['place']+f"。行动值：{budget['remaining']}/{budget['capacity']}。"
        if any(not m.get('read') for m in self.state['inbox']):text+='有未读交谈。'
        self.r.update_inputs(e['actor'],'npc:status',tail=[text])

def look(b,p):
    actor=p['actor'];m=person(b,actor);a=m.state;address=instance(b,a['place'],'world.address')
    adjacent=[e.target_node_id for e in address.node.read_interfaces if e.target_node_id in b.network.nodes and 'world.address' in b.network.nodes[e.target_node_id].modules]
    return dict(clock=date(max(0,tick(b))),action_budget=instance(b,actor,'action.budget').status(period=tick(b)),self={k:deepcopy(a[k]) for k in ('name','gender','role','coins','stamina','inventory','spouse','children')},
      location=dict(id=a['place'],name=address.node.name,service=address.config['service']),neighbors=[dict(id=k,name=b.network.nodes[k].name) for k in adjacent],
      people=[dict(id=k,name=v.state['name']) for k,v in residents(b).items() if k!=actor and v.state['place']==a['place']],
      pregnancies=[dict(id=k,due=date(v['due_tick']),ready=tick(b)>=v['due_tick']) for module in b.modules.find('world.family') for k,v in module.state['pregnancies'].items() if v['carrier']==actor and not v.get('child')],
      knowledge=instance(b,actor,'world.knowledge').references(),last_result=a.get('last_result'),
      finished=instance(b,actor,'agent.signal').state.get('status')!='running')
def messages(b,p):
    a=person(b,p['actor']).state;items=deepcopy([v for v in a['inbox'] if not v.get('read')])
    for v in a['inbox']:v['read']=True
    return dict(items=items)
def register(s):
    s.node_module('world.resident',Resident)
    s.rpc('world_look',look)
    s.rpc('world_messages',messages,mutation=True)
