"""概率事件组件：按触发动作独立抽取事件，并持久记录每个事件的命中次数。"""
import copy
import random

from datanet.studio.contract import StudioModule


class Module(StudioModule):
    """config.events 是一组互相独立的事件；state.counts 只保存每个事件的命中次数。"""

    def setup(self):
        # 配置在这里做跨字段检查：概率范围、触发动作、唯一 id 和命中上限。
        self._events()
        counts = self.state.get('counts')
        if not isinstance(counts, dict):
            counts = {}
        # 只保留合法计数，避免损坏的存档过不了 state_schema。
        self.state['counts'] = {
            key: value
            for key, value in counts.items()
            if isinstance(key, str) and key and type(value) is int and value >= 0
        }

    def draw(self, trigger, context=None):
        """抽取快照：对每个适用事件独立判定一次，返回本次命中的事件。

        trigger 必须是字符串；context 只被接受和校验，不参与概率计算。
        每个事件各自比较自己的固定概率，命中才增加计数；没有权重或保底机制。
        """
        if not isinstance(trigger, str) or not trigger.strip():
            raise ValueError('trigger 必须是非空字符串')
        if context is None:
            context = {}
        if not isinstance(context, dict):
            raise ValueError('context 必须是对象')

        counts = self.state['counts']
        events = []
        for event in self._events():
            if trigger not in event['triggers']:
                continue
            hits = counts.get(event['id'], 0)
            limit = event['max_hits']
            if limit is not None and hits >= limit:
                continue
            if not self._hits(event['probability']):
                continue
            counts[event['id']] = hits + 1
            events.append({
                'id': event['id'],
                'message': event['message'],
                'effects': copy.deepcopy(event['effects']),
            })
        return {'events': events}

    @staticmethod
    def _hits(probability):
        """0 和 1 直接短路，保证稳定；其余用标准 random 做一次独立伯努利判定。"""
        if probability <= 0:
            return False
        if probability >= 1:
            return True
        return random.random() < probability

    def _events(self):
        configured = self.config.get('events')
        if not isinstance(configured, (list, tuple)):
            raise ValueError('config.events 必须是数组')
        result = []
        seen = set()
        for index, raw in enumerate(configured):
            if not isinstance(raw, dict):
                raise ValueError('config.events[%d] 必须是对象' % index)
            event_id = raw.get('id')
            if not isinstance(event_id, str) or not event_id.strip():
                raise ValueError('config.events[%d].id 必须是非空字符串' % index)
            if event_id in seen:
                raise ValueError('config.events 中存在重复 id：' + event_id)
            seen.add(event_id)

            triggers = raw.get('triggers')
            if not isinstance(triggers, (list, tuple)) or not triggers:
                raise ValueError('config.events[%d].triggers 必须是非空字符串数组' % index)
            if any(not isinstance(item, str) or not item.strip() for item in triggers):
                raise ValueError('config.events[%d].triggers 必须是非空字符串数组' % index)

            probability = raw.get('probability')
            if type(probability) not in (int, float):
                raise ValueError('config.events[%d].probability 必须是 0 到 1 的数字' % index)
            probability = float(probability)
            if not 0 <= probability <= 1:
                raise ValueError('config.events[%d].probability 必须是 0 到 1 的数字' % index)

            max_hits = raw.get('max_hits')
            if max_hits is not None and (type(max_hits) is not int or max_hits < 0):
                raise ValueError('config.events[%d].max_hits 必须是 null 或非负整数' % index)

            message = raw.get('message')
            if not isinstance(message, str):
                raise ValueError('config.events[%d].message 必须是字符串' % index)

            result.append({
                'id': event_id,
                'triggers': tuple(triggers),
                'probability': probability,
                'max_hits': max_hits,
                'message': message,
                'effects': raw.get('effects'),
            })
        return result
