"""Explicit operator module: observe and request finite pulses; no business settlement."""
import asyncio
from threading import Lock,Thread
from datanet.core.node_modules import NodeModule
from datanet.core.json_values import freeze
from datanet.world.model import residents,date,tick,instance

class Operator(NodeModule):
    def install(self):self.lock=Lock();self.loop=None;self.thread=None
    def bind(self,r):self.r=r
    def observe(self,target=None):
        b=self.backend;people=residents(b)
        if target:
            if target not in people:raise ValueError('Unknown resident')
            return dict(clock=date(max(0,tick(b))),resident=people[target].state,binding=b.agents.get(target),activity=instance(b,target,'agent.signal').state)
        return dict(clock=date(max(0,tick(b))),actors={k:v.state for k,v in people.items()},
            activities={k:instance(b,k,'agent.signal').state for k in people},pulse=b.network.nodes[self.config['pulse']].state,
            places=[dict(id=m.node.node_id,name=m.node.name) for m in b.modules.find('world.address')])
    async def cycle(self,targets,timeout,execution_id):
        self.r.local.execution_id=execution_id
        try:
            pulse=self.backend.network.nodes[self.config['pulse']]
            pulse.content=freeze(dict(task=self.config['task'],timeout_ms=min(90000,int(timeout*1000))))
            result=await pulse.run(self.backend.signals,cycles=1,timeout_seconds=timeout,allow_partial=True)
            return dict(pulse=result,activities={target:dict(instance(self.backend,target,'agent.signal').state) for target in targets})
        finally:self.r.local.execution_id=None
    def run(self,targets,timeout):
        if not self.lock.acquire(blocking=False):raise RuntimeError('Another scene pulse is active')
        try:
            self.backend.modules.bind(self.r)
            from datanet.core.interface import Interface
            # Finite operator selection controls signal recipients; no per-round action store.
            with self.backend._transaction_lock:
                clock=self.backend.network.nodes[self.config['clock']]
                clock.write_interfaces=[Interface(t,{'threshold':1,'channels':self.config['channels']}) for t in targets]
                self.backend.dispatch('save',{})
            if not self.loop:
                self.loop=asyncio.new_event_loop();self.thread=Thread(target=self.loop.run_forever,name='scene-signals',daemon=True);self.thread.start()
            future=asyncio.run_coroutine_threadsafe(self.cycle(targets,timeout,getattr(self.r.local,'execution_id',None)),self.loop)
            try:return future.result(timeout=timeout+15)
            except BaseException:future.cancel();raise
        finally:self.lock.release()
    def close(self):
        super().close()
        if not self.loop:return
        future=asyncio.run_coroutine_threadsafe(self.backend.signals.close(),self.loop)
        try:future.result(timeout=5)
        finally:self.loop.call_soon_threadsafe(self.loop.stop);self.thread.join(timeout=5);self.loop.close();self.loop=None

def register(s):s.node_module('scene.operator',Operator)
