"""将节点上声明的模块信号接收方法绑定到独立运行器。"""

import asyncio

from domain.core.channel_filters import matches


class ModuleSignals:
    def __init__(self, runtime):
        self.runtime = runtime
        self.bound = []

    def clear(self):
        for node_id in self.bound:self.runtime.unbind(node_id)
        self.bound.clear()

    def refresh(self):
        self.clear()
        for node in self.runtime.network:
            modules = tuple(module for module in node.modules if hasattr(module, 'on_signal'))
            if not modules:continue
            node_id = node.info.node_id
            if node_id in self.runtime.bindings:raise ValueError('Node already has a host signal handler')

            async def receive(context, modules=modules):
                jobs = []
                for module in modules:
                    channels = module.config.get('signal_channels', module.signal_channels)
                    mode = module.config.get('channel_modes', {}).get('signal_channels', 'allow')
                    if matches(channels, context.signal.channels, mode):jobs.append(module.on_signal(context))
                return await asyncio.gather(*jobs)

            self.runtime.bind(node_id, receive, access_strength=lambda modules=modules:max(module.strength for module in modules))
            self.bound.append(node_id)
