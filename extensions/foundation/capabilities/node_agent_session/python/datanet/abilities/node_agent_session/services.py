"""Explicit reusable node module; active only when mounted."""
import asyncio
from datanet.core.node_modules import NodeModule
OWNER="capabilities/node_agent_session"

def text(r,value):return r.resource(value['component'],value['file']) if isinstance(value,dict) else value


class Session(NodeModule):
    bind_order=10
    def bind(self,r):
        actor=self.node.node_id
        if actor in r.states:return
        old=r.backend.agents.get(actor)
        r.plugins['capabilities/agent_runtime'].create(actor,text(r,self.config['prompt']),self.config.get('manager','root'),self.config.get('strength',2),self.config.get('toolboxes',[]),self.config.get('role'),binding=old,resume=old is not None)



def register(s):
    s.node_module('agent.session',Session)
