from datanet.world.model import *
from datanet.core.component_registry import resource_directory
import json
TOOLS=json.loads((resource_directory(__file__).parents[2]/"tools.json").read_text(encoding="utf-8"))

class Repair(ActionModule):
    module_name='world.repair';tools=TOOLS
    def apply(self,actor,name,args):
        b=self.backend;a=person(b,actor).state;item=args['item']
        if item not in a['inventory']:raise ValueError('You do not own this tool')
        worker=person(b,self.config['worker']).state
        if worker['place']!=self.config['address']:raise ValueError('铁匠不在店内。')
        if any(v<1 for v in self.state['materials'].values()):raise ValueError('修理材料不足。')
        take(a,'coins',self.config.get('price',2));a['inventory'][item]=self.config.get('durability',5)
        for k in self.state['materials']:self.state['materials'][k]-=1
        worker['coins']+=self.config.get('price',2)
        return dict(item=item,durability=a['inventory'][item])
def register(s):s.node_module('world.repair',Repair)
