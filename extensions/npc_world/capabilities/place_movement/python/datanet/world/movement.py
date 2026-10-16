from datanet.world.model import *
from datanet.core.component_registry import resource_directory
import json
TOOLS=json.loads((resource_directory(__file__).parents[2]/"tools.json").read_text(encoding="utf-8"))

class Address(ActionModule):
    module_name='world.address';tools=TOOLS
    def bind(self,r):
        self.r=r
        if not self.listeners:self.listen(r,'capabilities/place_movement','node/tool-invoked',self.moved)
    def moved(self,e):
        if e['target']==self.node.node_id and e['tool']=='move_here':
            # The domain transaction has finished. Native conclude records the tool
            # result before closing the turn, without cancellation or another request.
            self.r.host('conclude')
    def apply(self,actor,name,args):
        b=self.backend;old=location(b,actor)
        if old!=self.node.node_id and not any(e.target_node_id==self.node.node_id for e in b.network.nodes[old].read_interfaces):raise PermissionError('Destination is not adjacent')
        presence(b,actor,self.node.node_id)
        return dict(arrived=self.node.node_id,destination=self.node.name,tick_finished=True)
def register(s):s.node_module('world.address',Address)
