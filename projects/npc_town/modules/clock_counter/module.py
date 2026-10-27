"""时钟计数和待办存档；先提交节点事务，再请求宿主保存。"""

from copy import deepcopy
from inspect import isawaitable

from domain.core import Module, access

_DEFAULT_LABELS = ("清晨", "上午", "下午", "傍晚", "夜晚")
_SEEN_LIMIT = 200


def _labels(config):
    labels = config.get("labels") or _DEFAULT_LABELS
    result = [str(label) for label in labels if str(label)]
    return result or list(_DEFAULT_LABELS)


def _clock(config, tick):
    """返回公开时钟；初始计数 0 视为第一天的第一个时刻。"""
    labels = _labels(config)
    tick = max(0, int(tick))
    if tick == 0:
        day = 1
        slot = labels[0]
    else:
        day = (tick - 1) // len(labels) + 1
        slot = labels[(tick - 1) % len(labels)]
    return {"tick": tick, "day": day, "slot": slot}



class ClockCounterModule(Module):
    def __init__(self, transaction, checkpoint, config=None, state=None, **access_settings):
        super().__init__("clock.counter", **access_settings)
        self.transaction = transaction
        self.checkpoint = checkpoint
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        self.published = {}

    def _value(self):
        tick = int(self.state.get("tick", self.config.get("initial_tick", 0) or 0))
        return _clock(self.config, tick)

    async def read(self):
        return next(iter((await self._read()).values()))

    @access(channels=())
    async def _read(self, node):
        return self._value()

    async def receive(self, signal_id):
        return next(iter((await self._receive(signal_id)).values()))

    @access(channels=())
    async def _receive(self, node, signal_id):
        checkpoint_every = int(self.config.get("checkpoint_every", 0) or 0)
        checkpoint_due = False
        async with self.transaction([node.info.node_id], timeout=10):
            seen = [str(item) for item in (self.state.get("seen") or ())]
            if signal_id is not None and signal_id in seen:
                return self._value()
            tick = int(self.state.get("tick", self.config.get("initial_tick", 0) or 0)) + 1
            if signal_id is not None:
                seen = (seen + [signal_id])[-_SEEN_LIMIT:]
            self.state.update(tick=tick, seen=seen)
            value = self._value()
            self.published = dict(value)
            if self.config.get("write_text", False):
                node.dataer.write(self.config.get("text_template", "第{day}天 {slot}").format(**value))
            if checkpoint_every > 0 and tick % checkpoint_every == 0:
                self.state["pending_checkpoint"] = True
                checkpoint_due = True
        if checkpoint_due:
            await self._run_pending_checkpoint(node)
        return value

    async def _run_pending_checkpoint(self, node):
        if not self.state.get("pending_checkpoint", False):
            return False
        result = self.checkpoint(full=True)
        if isawaitable(result):await result
        async with self.transaction([node.info.node_id], timeout=10):
            self.state["pending_checkpoint"] = False
        return True

    async def flush(self):
        return next(iter((await self._flush()).values()))

    @access(channels=())
    async def _flush(self, node):
        checkpointed = await self._run_pending_checkpoint(node)
        return dict(checkpointed=checkpointed, tick=self._value()["tick"])
