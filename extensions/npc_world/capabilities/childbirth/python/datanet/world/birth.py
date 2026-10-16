from datanet.world.model import *
from datanet.core.component_registry import resource_directory
import json
TOOLS=json.loads((resource_directory(__file__).parents[2]/"tools.json").read_text(encoding="utf-8"))

from datanet.core.agent_node import AgentNode
from datanet.core.node import Node

def render(value,bindings):
    if isinstance(value,dict):return {key:render(v,bindings) for key,v in value.items()}
    if isinstance(value,list):return [render(v,bindings) for v in value]
    if isinstance(value,str):
        if value in bindings:return deepcopy(bindings[value])
        for key,replacement in bindings.items():
            if isinstance(replacement,str):value=value.replace(key,replacement)
    return value

class Birth(ActionModule):
    module_name='world.birth';tools=TOOLS
    def apply(self,actor,name,args):
        b=self.backend
        pair=next(((m,pid,v) for target in self.config['families'] for m in [instance(b,target,'world.family')] for pid,v in m.state['pregnancies'].items() if v['carrier']==actor and not v.get('child')),None)
        if not pair:raise ValueError('No pending pregnancy')
        family,pid,pregnancy=pair
        if tick(b)<pregnancy['due_tick']:raise ValueError('尚未到预产日。')
        child=self.config['child_prefix']+pid
        if child in b.network.nodes:raise ValueError('Child identity already exists')
        name='小芽'+pid[:3];parents=pregnancy['parents'];home=house(b,actor) or next((house(b,x) for x in parents if house(b,x)),None)
        bindings={'{{actor}}':child,'{{context}}':child+'/context','{{name}}':name,'{{place}}':self.config['address'],'{{parents}}':parents,'{{background}}':'你的父母是'+'、'.join(person(b,parent).state['name'] for parent in parents)+'。你刚在医院出生，已经能说话。','{{home_text}}':('你住在'+b.network.nodes[home.config['address']].name+'。') if home else '你目前没有登记住处。'}
        spec=render(self.config['child_template'],bindings)
        resident=AgentNode(child,name,file_path=b.directory/'world/memories'/(pid+'.md'));resident.write_memory('# '+name+'的私人记忆\n')
        b.network.add_node(resident);assembly=Node(child+'/context',name+'的上下文',None);b.network.add_node(assembly)
        assembly.read_interfaces=[Interface(**e) for e in spec['context_reads']]
        for target,entries in ((child,spec['actor_modules']),(child+'/context',spec['context_modules'])):
            for key,value in entries.items():b.modules.mount(target,key,**value,bind=False)
        resident.read_interfaces=[Interface(child+'/context',{'threshold':1,'visibility':'private'}),Interface(spec['common'],{'threshold':1})]
        resident.write_interfaces=[Interface(spec['signal_return'],{'threshold':1,'channels':spec['channels']})]
        presence(b,child,self.config['address'])
        if home:home.state['residents'].append(child)
        pregnancy['child']=child
        for parent in parents:person(b,parent).state['children'].append(child)
        return dict(child=child,notice='儿童在下一次脉冲加入。')
def register(s):s.node_module('world.birth',Birth)
