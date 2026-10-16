from datanet.world.model import *
from datanet.core.component_registry import resource_directory
import json
TOOLS=json.loads((resource_directory(__file__).parents[2]/"tools.json").read_text(encoding="utf-8"))

class Information(ActionModule):
    module_name='world.information';tools=TOOLS
    def apply(self,actor,name,args):
        result=dict(address=self.config['address'],services=[n for n in self.node.expose if n!='local_info'])
        for name in ('world.trade','world.repair'):
            if name in self.node.modules:result[name]=deepcopy(self.node.modules[name])
        return result
def register(s):s.node_module('world.information',Information)
