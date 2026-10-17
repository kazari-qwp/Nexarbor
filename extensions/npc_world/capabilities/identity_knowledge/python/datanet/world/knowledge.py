from datanet.world.model import *

from datanet.core.metadata import lookup

class Knowledge(NodeModule):
    bind_order=-20
    def matched(self):
        values=self.backend.network.get_metadata(self.node.node_id);result=[]
        for spec in self.config['profiles']:
            try:matched=all((lookup(values,k) in v if isinstance(v,list) else lookup(values,k)==v) for k,v in spec['when'].items())
            except (KeyError,IndexError):matched=False
            if matched:result.append(spec)
        return result
    def sync(self):
        b=self.backend;assembly=b.network.nodes[self.config['context']]
        for node in (self.node,assembly):node.interfaces[:]=[e for e in node.interfaces if not e.metadata.attributes.get('identity_knowledge')]
        for spec in self.matched():
            for node in (self.node,assembly):node.interfaces.append(Interface(spec['node_id'], {'threshold': 1, 'visibility': 'private', 'attributes': {'identity_knowledge': True}, 'channels': ['access.read']}))
    def references(self):return [dict(node_id=s['node_id'],name=s['name'],delivery=s['delivery']) for s in self.matched()]
    def bind(self,r):
        self.sync()
        if not self.listeners:
            self.listen(r,'capabilities/identity_knowledge','agent/pre-step',lambda e:self.sync() if e['actor']==self.node.node_id else None)
            self.listen(r,'capabilities/identity_knowledge','context/prepare',lambda e:self.sync() if e['actor']==self.node.node_id else None)
            # Access grants must reflect current metadata before the assembler reads.
            for app,event,entry in self.listeners:
                app.listeners[event].remove(entry);app.listeners[event].insert(0,entry)
    def unmount(self):
        for node_id in (self.node.node_id,self.config['context']):
            node=self.backend.network.nodes[node_id]
            node.interfaces[:]=[e for e in node.interfaces if not e.metadata.attributes.get('identity_knowledge')]
        super().unmount()

def register(s):s.node_module('world.knowledge',Knowledge)
