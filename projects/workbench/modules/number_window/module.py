import math

from copy import deepcopy
from domain.core import Module, access

MAX_RECEIPTS = 200


def _window_size(module):
    raw = module.config.get("window_size", 3)
    if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= 1000:
        return 3
    return raw


def _list_state(module, name):
    value = module.state.get(name)
    if isinstance(value, list):
        return value
    if value is None:
        value = []
    else:
        value = list(value)
    module.state[name] = value
    return value


def _keep_recent(values, limit):
    if len(values) > limit:
        del values[: len(values) - limit]


def _stats(values, window_size):
    count = len(values)
    if count == 0:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "window_size": window_size,
        }
    return {
        "count": count,
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / count,
        "window_size": window_size,
    }


def _is_finite_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


class NumberWindowModule(Module):
    def __init__(self, config=None, state=None, **access_settings):
        super().__init__('number.window', **access_settings)
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})

    async def push(self, value, key=None):
        return next(iter((await self._operate('push', {'value': value, 'key': key})).values()))

    async def read(self):
        return next(iter((await self._operate('read', {})).values()))

    @access(channels=())
    async def _operate(self, node, operation, parameters):
        window_size = _window_size(self)
        window = _list_state(self, 'window')
        receipts = _list_state(self, 'receipts')
        _keep_recent(window, window_size)
        _keep_recent(receipts, MAX_RECEIPTS)
        if operation == 'read':
            return {**_stats(window, window_size), 'values': list(window)}

        value = parameters.get('value')
        if not _is_finite_number(value):
            raise ValueError('数值必须是有限数字，不能是 NaN 或 Infinity')
        key = parameters.get('key')
        if key is not None:
            if not isinstance(key, str) or not key:
                raise ValueError('请求键必须是非空字符串')
            for receipt in receipts:
                if receipt.get('key') != key:
                    continue
                if receipt.get('value') == value:
                    return {**_stats(window, window_size), 'duplicate': True}
                raise ValueError('相同请求键已用于不同数值，不能重复提交不同值')
            receipts.append({'key': key, 'value': value})
            _keep_recent(receipts, MAX_RECEIPTS)
        window.append(value)
        _keep_recent(window, window_size)
        self.state['window'] = window
        self.state['receipts'] = receipts
        return {**_stats(window, window_size), 'duplicate': False}
