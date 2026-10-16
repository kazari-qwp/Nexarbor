from datanet.world.model import *
from datanet.core.component_registry import resource_directory
import json
TOOLS=json.loads((resource_directory(__file__).parents[2]/"tools.json").read_text(encoding="utf-8"))

class Refreshment(ActionModule):
    module_name='world.refreshment';tools=TOOLS
    def apply(self,actor,name,args):
        a=person(self.backend,actor).state;take(a,'coins',self.config.get('price',1));a['stamina']=min(5,a['stamina']+self.config.get('restore',1));return dict(stamina=a['stamina'])
def register(s):s.node_module('world.refreshment',Refreshment)
