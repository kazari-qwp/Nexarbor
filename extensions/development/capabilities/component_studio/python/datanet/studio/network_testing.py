"""Repeatable author tests against the same real graph used by test_environment."""
from pathlib import Path
from copy import deepcopy
import asyncio,importlib.util,json,os,shutil,tempfile
from functools import cache
from .environment import open_backend
from datanet.core.storage_paths import storage_path


@cache
def _executor_type():
    from .service import PROJECT
    spec=importlib.util.spec_from_file_location('nexarbor_test_executor',PROJECT/'adapters/harness/studio/executor.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.NativeExecutor


class NetworkHarness:
    def __init__(self,fixture=None,*,network_file=None):
        source=Path(fixture or os.environ['DATANET_TEST_ENVIRONMENT']).resolve()
        if not (source/'initial.json').is_file() or not (source/'setup.json').is_file():
            raise ValueError('需要由 validate 创建的隔离网络夹具')
        if network_file is not None:
            views=json.loads((source/'setup.json').read_text('utf-8')).get('views',{})
            if network_file not in views:raise ValueError('未知网络产物；先在 outputs.json 中声明并验证')
            source=Path(views[network_file])
        self._temporary=tempfile.TemporaryDirectory(prefix='network-test-',dir=storage_path(tempfile.gettempdir()))
        self.home=Path(self._temporary.name)
        shutil.copytree(source,self.home,dirs_exist_ok=True)
        self.backend=open_backend(self.home)
        self._ports=[]
        self._executions=json.loads((self.home/'setup.json').read_text('utf-8')).get('executions',{})
        self._executor=None
        self._agent_callback=None
        self.last_agent_views={}

    @property
    def network(self):return self.backend.network

    def register_tools(self,provider,definitions,execute):
        """Explicit deterministic port double; normal grants and routing still apply."""
        if provider=='runtime' and any(item['name']=='agent_run' for item in definitions):raise ValueError('不要替换整个官方 Agent 运行端口；用 h.register_agent(callback) 仅替换模型正文')
        from .port_testing import checked_executor
        checked=checked_executor(provider,definitions,execute,self.backend.port_contracts)
        self._ports.append((provider,definitions,checked))
        self.backend.external_tools.register(provider,definitions,checked)

    def register_agent(self,callback):
        from .agent_testing import register_agent
        self._agent_callback=callback
        register_agent(self.backend,callback,prepare=self.prepare_agent,acknowledge=self.acknowledge_agent,views=self.last_agent_views)

    async def call(self,actor,node,module,operation,parameters=None,*,strength=2,channels=()):
        return await self.backend.modules.access(actor,node,module,operation,parameters or {},strength=strength,channels=list(channels))

    async def invoke(self,actor,target,ref,parameters=None,*,strength=2,channels=()):
        return await self.backend.external_tools.invoke(actor,target,ref,parameters or {},strength=strength,channels=list(channels))

    async def emit(self,actor,channels,*,strength=3,content=None,signal_id=None):
        from datanet.core.signals import Signal
        options=dict(content=content,node_timeout_seconds=5,timeout_seconds=15)
        if signal_id is not None:options['signal_id']=signal_id
        return await self.backend.signals.propagate(Signal(actor,list(channels),strength,**options))

    async def run_pulse(self,pulse,*,cycles=1,timeout_seconds=15,expect_complete=True):
        """Same configured entry point as the client; do not replace its channels/strength."""
        node=self.network.nodes[pulse]
        if node.signal_type!='pulse':raise ValueError('需要候选实际的脉冲节点')
        result=await node.run(self.backend.signals,cycles=cycles,timeout_seconds=timeout_seconds)
        self.last_pulse_report=result
        if expect_complete and (result['status']!='completed' or result['cycles']!=cycles):
            wave=result['reports'][-1] if result['reports'] else {}
            raise AssertionError(f"脉冲 {pulse} 未完成：status={result['status']}，轮数={result['cycles']}/{cycles}，传播={wave.get('status')}，回源={wave.get('returned')}。核对真实闭环、接收器和强度；完整报告在 h.last_pulse_report，负向测试用 expect_complete=False。")
        return result

    def apply_context(self,actor,packet,source='prepare:test'):
        from .context_packets import apply_context_packet
        if not apply_context_packet(self.backend,actor,source,packet):raise ValueError('需要 nexarbor-context/v1 准备结果')
        return self.network.nodes[actor].inputs.snapshot()

    def _agent_command(self,actor,command,**parameters):
        # Restore only the producer's actual binding while exercising the formal
        # preparation/ack contract. Real model and external execution stay denied.
        if self._executor is None:
            previous_executor=self.backend.agent_executor
            self._executor=_executor_type()(self.backend,None)
            self.backend.agent_executor=previous_executor
        with self.backend.node_locks.access_sync([actor]):
            node=self.network.nodes[actor];previous=node.execution_binding
            binding=previous or self._executions.get(actor)
            if not binding:raise ValueError('候选没有为此 Agent 配置执行绑定；不能由测试补装')
            node.execution_binding=deepcopy(binding)
            try:
                if command=='prepare':
                    _,effective=self._executor.binding(actor)
                    self.backend.runtime.run(self._executor.module_tools.visit(actor,actor,strength=effective.get('strength',0),channels=effective.get('channels',[])))
                return getattr(self._executor,command)(dict(actor=actor,**parameters))
            finally:node.execution_binding=previous

    async def prepare_agent(self,actor):
        """Actual executor preparation: system/context/pending inputs/tail/tools, no model call."""
        from datanet.core.access_budget import current_access,active_agent
        frame=current_access.set(None);identity=active_agent.set(None)
        try:
            async with self.backend.node_locks.suspend_access():
                return await asyncio.to_thread(self._agent_command,actor,'prepare')
        finally:active_agent.reset(identity);current_access.reset(frame)

    async def acknowledge_agent(self,actor,events):
        """Acknowledge exactly the input events consumed by a simulated model request."""
        return await asyncio.to_thread(self._agent_command,actor,'ack',events=events)

    async def agent_tool(self,actor,name,arguments=None):
        """Simulate a model tool call through the actual executor's routes and grants."""
        from datanet.core.access_budget import current_access,active_agent
        frame=current_access.set(None);identity=active_agent.set(None)
        try:
            async with self.backend.node_locks.suspend_access():
                return await asyncio.to_thread(self._agent_command,actor,'invoke',name=name,arguments=arguments or {})
        finally:active_agent.reset(identity);current_access.reset(frame)

    async def _close_signals(self):
        # Model tools enter the actual Backend runtime loop; direct author calls
        # may use the test loop. Cancel and join each delivery on its owning loop.
        signals=self.backend.signals
        async def settle(tasks):
            await asyncio.gather(*tasks,return_exceptions=True)
        for _ in range(3):
            active=[task for task in list(signals._active.values()) if task is not asyncio.current_task()]
            if not active:break
            groups={};current=asyncio.get_running_loop()
            for task in active:groups.setdefault(task.get_loop(),[]).append(task)
            for loop,tasks in groups.items():
                for task in tasks:
                    if loop is current:task.cancel()
                    else:loop.call_soon_threadsafe(task.cancel)
            for loop,tasks in groups.items():
                if loop is current:await settle(tasks)
                else:await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(settle(tasks),loop))
        await signals.close()

    async def restart(self):
        """Persist, close and reopen the actual checkpoint store, with test ports restored."""
        await self._close_signals()
        self.backend.dispatch('save',{})
        self.backend.close()
        self.backend=open_backend(self.home)
        self._executor=None
        for provider,definitions,execute in self._ports:self.backend.external_tools.register(provider,definitions,execute)
        if self._agent_callback:self.register_agent(self._agent_callback)

    async def close(self):
        try:await self._close_signals()
        finally:
            try:self.backend.close()
            finally:self._temporary.cleanup()
