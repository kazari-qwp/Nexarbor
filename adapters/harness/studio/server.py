"""Dedicated v7 development host; old application components are not loaded."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import config
from transport import Transport
from datanet.core.backend import Backend
from remote import HarnessRemote
from executor import NativeExecutor
import asyncio
import os,json

class StudioTransport(Transport):
    def dispatch(self,method,p):
        # Long Agent work yields to callback RPCs; each tool still commits atomically.
        if method=='studio_pulse':return self.backend.studio.pulse(p)
        if method=='executor_run':return asyncio.run(self.backend.execute_agent(p['actor'],p.get('text','')))
        if method=='executor_read':
            node=self.backend.network.nodes[p['actor']]
            return self.host('agent-read',dict(actor=node.node_id,name=node.name,session_id=self.backend.agents.get(node.node_id,{}).get('session_id')))
        return super().dispatch(method,p)

def main():
    initial=os.environ.get('DATANET_INITIAL_NETWORK')
    document=json.loads(Path(initial).read_text(encoding='utf-8')) if initial else None
    backend=Backend(sys.argv[1],initial_document=document);remote=HarnessRemote(backend.studio)
    for method in ['connect','start','read','cancel','status']:
        backend.components.rpc('studio_agent_'+method,lambda b,p,method=method:getattr(remote,method)(p))
    backend.components.finalizers.append(lambda b:remote.close())
    transport=StudioTransport(backend);NativeExecutor(backend,transport)
    transport.run(sys.stdin)

if __name__=='__main__':
    sys.stdin.reconfigure(encoding='utf-8');sys.stdout.reconfigure(encoding='utf-8');main()
