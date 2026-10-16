from datanet.world.model import *
from datanet.core.component_registry import resource_directory
import json
TOOLS=json.loads((resource_directory(__file__).parents[2]/"tools.json").read_text(encoding="utf-8"))

class Gather(ActionModule):
    module_name='world.gather'
    def install(self):
        self.tools={self.config['tool_name']:TOOLS[self.config['tool_name']]};super().install()
    def apply(self,actor,name,args):
        a=person(self.backend,actor).state;tool=self.config['item'];resource=self.config['resource'];cost=self.config.get('cost',1)
        if a['stamina']<cost or a['inventory'].get(tool,0)<1:raise ValueError('需要体力和耐久大于0的工具。')
        a['stamina']-=cost;a['inventory'][tool]-=1;add(a,resource,self.config.get('yield',2))
        return dict(resource=resource,quantity=self.config.get('yield',2))
def register(s):s.node_module('world.gather',Gather)
