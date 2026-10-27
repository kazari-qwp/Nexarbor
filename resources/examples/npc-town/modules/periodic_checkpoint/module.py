"""只计信号次数并定期保存；失败的保存保留待办供 flush 重试。"""

from copy import deepcopy
from inspect import isawaitable
from domain.core import Module, access


class PeriodicCheckpointModule(Module):
    signal_channels = ('tick',)

    async def on_signal(self, context):
        return await self.receive(context.signal.signal_id)

    def __init__(self, transaction, checkpoint, config=None, state=None, **access_settings):
        super().__init__("runtime.periodic_checkpoint", **access_settings)
        self.transaction = transaction
        self.checkpoint = checkpoint
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})

    def _value(self):
        return dict(count=self.state.get("count", 0), pending=self.state.get("pending", False))

    async def read(self):
        return next(iter((await self._read()).values()))

    @access(channels=())
    async def _read(self, node):
        return self._value()

    async def _flush(self, node):
        if not self.state.get("pending", False):return False
        result = self.checkpoint(full=True)
        if isawaitable(result):await result
        async with self.transaction([node.info.node_id]):self.state["pending"] = False
        return True

    async def flush(self):
        return next(iter((await self._flush_local()).values()))

    @access(channels=())
    async def _flush_local(self, node):
        await self._flush(node)
        return self._value()

    async def receive(self, signal_id):
        return next(iter((await self._receive(signal_id)).values()))

    @access(channels=())
    async def _receive(self, node, signal_id):
        async with self.transaction([node.info.node_id]):
            if signal_id not in self.state.get("seen", []):
                count = self.state.get("count", 0) + 1
                self.state["count"] = count
                self.state["seen"] = (list(self.state.get("seen", [])) + [signal_id])[-200:]
                if count % self.config.get("every", 5) == 0:self.state["pending"] = True
        await self._flush(node)
        return self._value()
