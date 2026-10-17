from datanet.world.model import *
from datanet.core.component_registry import resource_directory
import json
TOOLS=json.loads((resource_directory(__file__).parents[2]/"tools.json").read_text(encoding="utf-8"))

class Address(ActionModule):
    module_name='world.address';tools=TOOLS
    def apply(self,actor,name,args):
        b=self.backend;old=location(b,actor)
        if old!=self.node.node_id and not any(e.target_node_id==self.node.node_id for e in b.network.nodes[old].interfaces):raise PermissionError('Destination is not adjacent')
        presence(b,actor,self.node.node_id)
        return dict(arrived=self.node.node_id,destination=self.node.name)
def register(s):s.node_module('world.address',Address)
