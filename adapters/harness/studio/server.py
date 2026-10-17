"""Dedicated v7 development host; old application components are not loaded."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import config
from transport import Transport
from datanet.core.backend import Backend
from remote import HarnessRemote

def main():
    backend=Backend(sys.argv[1]);remote=HarnessRemote(backend.studio)
    for method in ['connect','start','read','cancel','status']:
        backend.components.rpc('studio_agent_'+method,lambda b,p,method=method:getattr(remote,method)(p))
    backend.components.finalizers.append(lambda b:remote.close())
    Transport(backend).run(sys.stdin)

if __name__=='__main__':
    sys.stdin.reconfigure(encoding='utf-8');sys.stdout.reconfigure(encoding='utf-8');main()
