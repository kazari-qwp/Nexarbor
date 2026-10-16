from datanet.world.model import *
from datanet.core.component_registry import resource_directory
import json
TOOLS=json.loads((resource_directory(__file__).parents[2]/"tools.json").read_text(encoding="utf-8"))

class Household(ActionModule):
    module_name='world.household';tools=TOOLS
    def apply(self,actor,name,args):
        if actor not in self.state['residents']:raise PermissionError('只能在自己登记居住的居民楼休息。')
        a=person(self.backend,actor).state;a['stamina']=min(self.config.get('stamina_cap',5),a['stamina']+self.config.get('restore',3))
        return dict(stamina=a['stamina'])
def register(s):s.node_module('world.household',Household)
