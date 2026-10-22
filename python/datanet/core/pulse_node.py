"""Core pulse source: finite closed-loop emission, with no application rules."""
import asyncio
import inspect
import time
from contextlib import asynccontextmanager
from copy import deepcopy
from .node import Node
from .signals import Signal
from .json_values import freeze,thaw,names
from .interface import validate_strength

class PulseNode(Node):
    signal_type='pulse'

    @asynccontextmanager
    async def _access(self,runtime):
        locks=getattr(runtime.network,'node_locks',None)
        if locks:
            async with locks.access([self.node_id]):yield
        else:yield

    async def _update(self,runtime,**values):
        async with self._access(runtime):self.state.update(values)

    def __init__(self,node_id,name,data_kind=None,*,channels=('pulse',),strength=3,content=None,signal_options=None,state=None,description='',aggregation='sum'):
        super().__init__(node_id,name,'pulse',description=description,aggregation=aggregation)
        self.channels=names(channels,'channels',allow_empty=False)
        self.strength=validate_strength(strength);self.content=freeze(content)
        self.signal_options=freeze(signal_options or {})
        allowed={'failure_policy','max_hops','max_deliveries','timeout_seconds','node_timeout_seconds'}
        if set(self.signal_options)-allowed:raise ValueError('Invalid pulse signal option')
        Signal(node_id,self.channels,strength,content=self.content,**thaw(self.signal_options))
        self.state=deepcopy(state) if state is not None else dict(sequence=0,phase='idle',active_signal=None,last_signal=None,last_status=None)
        self._running=False
        self._validate_state()
        if self.state['phase'] in ('propagating','finalizing'):
            self.state['phase']='interrupted'
            self.state['error']='Pulse execution was interrupted; reconcile effects before starting again'

    def _validate_state(self):
        required={'sequence','phase','active_signal','last_signal','last_status'}
        if not isinstance(self.state,dict) or not required<=self.state.keys():raise ValueError('Invalid pulse state')
        if type(self.state['sequence']) is not int or self.state['sequence']<0:raise ValueError('Invalid pulse sequence')
        if self.state['phase'] not in ('idle','propagating','finalizing','interrupted','blocked','completed'):raise ValueError('Invalid pulse phase')
        freeze(self.state)

    def reconcile(self,reason):
        if self._running:raise RuntimeError('Pulse is running')
        if not isinstance(reason,str) or not reason.strip():raise ValueError('Reconciliation reason required')
        self.state.update(phase='idle',active_signal=None,reconciliation=reason)

    async def run(self,runtime,*,cycles=1,timeout_seconds=86400,cycle_complete=None,allow_partial=False):
        if type(cycles) is not int or cycles<1:raise ValueError('A positive finite cycle count is required')
        validate_strength(timeout_seconds)
        if not 0<timeout_seconds<=86400:raise ValueError('Invalid pulse runtime deadline')
        if type(allow_partial) is not bool:raise ValueError('allow_partial must be boolean')
        if runtime.network.nodes.get(self.node_id) is not self:raise ValueError('Pulse must belong to the runtime network')
        if cycle_complete is not None and not callable(cycle_complete):raise TypeError('Invalid cycle completion handler')
        async with self._access(runtime):
            if self._running:raise RuntimeError('Pulse is already running')
            if self.state['phase']=='interrupted':raise RuntimeError('Reconcile the interrupted pulse before restarting')
            self._running=True
        deadline=time.monotonic()+max(86400,timeout_seconds);reports=[]
        try:
            for _ in range(cycles):
                left=deadline-time.monotonic()
                if left<=0:
                    await self._update(runtime,phase='blocked',error='Pulse runtime deadline exceeded')
                    break
                async with self._access(runtime):
                    options=thaw(self.signal_options)
                    options['timeout_seconds']=min(max(86400,options.get('timeout_seconds',86400)),left)
                    signal=Signal(self.node_id,self.channels,self.strength,content=self.content,
                                  kind='pulse',close_loop=True,parent_id=self.state['last_signal'],sequence=self.state['sequence']+1,**options)
                    runtime._authorize(signal)
                    self.state.pop('error',None)
                    self.state.update(sequence=signal.sequence,phase='propagating',active_signal=signal.signal_id)
                await runtime._save()
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('Pulse runtime deadline exceeded')
                report=await asyncio.wait_for(runtime.propagate(signal),remaining);reports.append(report)
                await self._update(runtime,last_signal=signal.signal_id,last_status=report['status'])
                if not report['returned'] or report['status'] not in (('completed','partial') if allow_partial else ('completed',)):
                    await self._update(runtime,phase='blocked',active_signal=None);await runtime._save();break
                await self._update(runtime,phase='finalizing');await runtime._save()
                if cycle_complete:
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise TimeoutError('Pulse completion deadline exceeded')
                    async with self._access(runtime):
                        result=cycle_complete(self,deepcopy(report))
                        if not inspect.isawaitable(result):raise TypeError('Cycle completion handler must be asynchronous')
                        await asyncio.wait_for(result,remaining)
                await self._update(runtime,phase='completed',active_signal=None)
                await runtime._save()
        except BaseException:
            active=self.state['active_signal']
            # Pulse owns this wave. Cancelling only its shielded waiter would
            # leave receivers working after the pulse has reported failure.
            if active and await runtime.cancel(active):
                try:await runtime.wait(active)
                except asyncio.CancelledError:pass
            async with self._access(runtime):
                if self.state['active_signal'] is not None:self.state['phase']='interrupted'
            await runtime._save()
            raise
        finally:self._running=False
        return dict(cycles=len(reports),requested_cycles=cycles,status=self.state['phase'],reports=reports)
