"""通用计数存档组件：按 world.tick 新信号计数，并按间隔请求全量存档。"""
from datanet.studio.contract import StudioModule

DEFAULT_INTERVAL = 5
RECENT_LIMIT = 128


class Module(StudioModule):
    """挂在普通节点上的计数器；不初始化整张网络，也不处理 NPC 收尾。"""

    def setup(self):
        count = self.state.get('count', 0)
        if type(count) is not int or count < 0:
            count = 0
        self.state['count'] = count
        self.state.setdefault('last_signal', None)
        recent = self.state.get('recent_signals')
        if not isinstance(recent, list):
            recent = []
        self.state['recent_signals'] = [item for item in recent if isinstance(item, str)][-RECENT_LIMIT:]

    def on_signal(self, context):
        signal_id = getattr(context.signal, 'signal_id', None)
        if not isinstance(signal_id, str) or not signal_id:
            return self._result(reused=True)
        recent = self.state['recent_signals']
        if signal_id == self.state['last_signal'] or signal_id in recent:
            return self._result(reused=True)
        self.state['count'] += 1
        self.state['last_signal'] = signal_id
        recent.append(signal_id)
        if len(recent) > RECENT_LIMIT:
            del recent[:len(recent) - RECENT_LIMIT]
        full = self.state['count'] % self._interval() == 0
        if full:
            self.backend.dispatch('save', {'full': True})
        return self._result(full=full)

    def get_count(self):
        return dict(count=self.state['count'], last_signal=self.state['last_signal'],
                    interval=self._interval())

    def _interval(self):
        value = self.config.get('interval', DEFAULT_INTERVAL)
        if type(value) is not int or value < 1:
            raise ValueError('interval 必须是正整数')
        return value

    def _result(self, full=False, reused=False):
        return dict(count=self.state['count'], full_snapshot=full, reused=reused)
