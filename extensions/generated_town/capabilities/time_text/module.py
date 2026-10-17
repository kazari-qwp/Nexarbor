"""时间文本组件：每个新的世界脉冲把时间推进一格，并写入挂载的文本节点。"""
from datanet.studio.contract import StudioModule


class Module(StudioModule):
    """一天包含 config.slots 里的若干时刻；state.tick 是累计推进的总时刻数，-1 表示尚未开始。"""

    def setup(self):
        tick = self.state.get('tick')
        if type(tick) is not int or tick < -1:
            self.state['tick'] = -1
        if not isinstance(self.state.get('last_signal_id'), str):
            self.state['last_signal_id'] = ''
        # 格式在装配时就检查，不等到第一个脉冲才暴露配置错误。
        self._template()

    def on_signal(self, context):
        signal_id = context.signal.signal_id
        # 同一信号重复送达：不推进、不重写文本。
        if signal_id == self.state['last_signal_id']:
            return self._report(False)
        tick = self.state['tick'] + 1
        # 先写文本再提交状态：写入失败时状态仍停在上一格，可由后续信号补上。
        self._write(self._text(tick))
        self.state['tick'] = tick
        self.state['last_signal_id'] = signal_id
        return self._report(True)

    def get_time(self):
        """当前天、时刻、总时刻和渲染文本；尚未开始时 day=0、slot=''、slot_index=-1、text=''。"""
        return self._read()

    def get_day(self):
        """当前天数（从 1 开始）；尚未开始时为 0。"""
        return dict(day=self._clock(self.state['tick'])['day'])

    def get_tick(self):
        """累计推进的总时刻数；-1 表示尚未开始，0 是第 1 天第一个时刻。"""
        return dict(tick=self.state['tick'])

    def _slots(self):
        slots = self.config.get('slots')
        if not isinstance(slots, (list, tuple)) or not slots:
            raise ValueError('config.slots 必须是非空字符串数组')
        if any(not isinstance(item, str) or not item for item in slots):
            raise ValueError('config.slots 必须是非空字符串数组')
        return slots

    def _template(self):
        template = self.config.get('format')
        if not isinstance(template, str) or not template.strip():
            raise ValueError('config.format 必须是非空字符串')
        try:
            template.format(day=1, slot=self._slots()[0], tick=0)
        except (AttributeError, IndexError, KeyError, ValueError) as error:
            raise ValueError('config.format 只能引用 {day}、{slot}、{tick}：' + str(error)) from None
        return template

    def _clock(self, tick):
        slots = self._slots()
        if tick < 0:
            # 尚未开始：没有天、时刻和文本，只有总时刻的 -1。
            return dict(day=0, slot='', slot_index=-1, tick=tick)
        size = len(slots)
        index = tick % size
        return dict(day=tick // size + 1, slot=slots[index], slot_index=index, tick=tick)

    def _text(self, tick):
        if tick < 0:
            return ''
        clock = self._clock(tick)
        return self._template().format(day=clock['day'], slot=clock['slot'], tick=clock['tick'])

    def _read(self):
        clock = self._clock(self.state['tick'])
        clock['text'] = self._text(self.state['tick'])
        return clock

    def _report(self, advanced):
        return dict(advanced=advanced, **self._read())

    def _write(self, text):
        result = self.node.write('content', text)
        status = getattr(result, 'status', 'ok')
        if status != 'ok':
            errors = getattr(result, 'errors', None) or ()
            raise RuntimeError('时间文本写入失败：' + ('; '.join(map(str, errors)) or str(status)))
