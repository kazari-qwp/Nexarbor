"""Owned codecs keep disabled world components dormant, including NPC memories."""
import os
from datanet.core.node import Node
from datanet.core.agent_node import AgentNode
from datanet.core.component_registry import NodeCodec,register_node

class WorldNode(Node):
    def __init__(self,node_id,name,data_kind=None,*,place='',kind='address',description=''):
        super().__init__(node_id,name,'world',description=description)
        self.place,self.kind=place,kind

class Resident(AgentNode):
    pass

def register():
    register_node(NodeCodec('world_place',WorldNode,
        lambda n,b:dict(place=n.place,kind=n.kind),
        lambda c,p,b:WorldNode(*c,**p),parameter_fields=['place','kind'],
        local_read=False,local_write=False,local_schema=False))
    register_node(NodeCodec('world_resident',Resident,
        lambda n,b:dict(file_path=os.path.relpath(n.file_path,b),creation_options=n.creation_options),
        lambda c,p,b:Resident(*c,file_path=b/p['file_path'],creation_options=p.get('creation_options')),
        parameter_fields=['file_path','creation_options'],resources=('file_path',),
        local_read=False,local_write=False,local_schema=False))
