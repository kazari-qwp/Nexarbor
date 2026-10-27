"""小镇时间：一次信号推进一格，更新时间文本和公开计数。"""

from copy import deepcopy
from domain.core import Module, access


def clock(module):
    tick = module.state.get("tick", module.config.get("initial_tick", 0))
    labels = module.config.get("labels") or ("早上", "中午", "下午", "傍晚", "午夜")
    return dict(tick=tick, day=(max(1, tick) - 1) // len(labels) + 1,
                slot=labels[(max(1, tick) - 1) % len(labels)])


class WorldTimeModule(Module):
    signal_channels = ('tick',)

    async def on_signal(self, context):
        return await self.receive(context.signal.signal_id)

    def __init__(self, transaction, config=None, state=None, **access_settings):
        super().__init__("world.time", **access_settings)
        self.transaction = transaction
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        self.published = {}

    async def read(self):
        return next(iter((await self._read()).values()))

    @access(channels=())
    async def _read(self, node):
        return clock(self)

    async def receive(self, signal_id):
        return next(iter((await self._receive(signal_id)).values()))

    @access(channels=())
    async def _receive(self, node, signal_id):
        async with self.transaction([node.info.node_id]):
            if signal_id not in self.state.get("seen", []):
                self.state["tick"] = clock(self)["tick"] + 1
                self.state["seen"] = (list(self.state.get("seen", [])) + [signal_id])[-200:]
                value = clock(self)
                node.dataer.write(self.config.get("text_template", "当前时间：第{day}天 {slot}（总 tick：{tick}）").format(**value))
                self.published = value
        return clock(self)
