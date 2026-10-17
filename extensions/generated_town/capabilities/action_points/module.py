"""通用行动值组件：每个新时刻恢复满额，供其他组件检查与扣除。"""
from datanet.studio.contract import StudioModule

DEFAULT_MAX = 10


class Module(StudioModule):
    """挂在 Agent 上的行动值余额；不包含移动、挖矿等具体业务。"""

    def setup(self):
        limit = self._limit()
        remaining = self.state.get('remaining', limit)
        if type(remaining) is int:
            remaining = max(0, min(remaining, limit))
        self.state['remaining'] = remaining
        self.state.setdefault('last_signal_id', None)

    def on_signal(self, context):
        limit = self._limit()
        signal_id = context.signal.signal_id
        if signal_id == self.state.get('last_signal_id'):
            return self._moment(False, limit)
        self.state['remaining'] = limit
        self.state['last_signal_id'] = signal_id
        return self._moment(True, limit)

    def get_balance(self):
        limit = self._limit()
        remaining = self.state['remaining']
        return dict(ok=True, remaining=remaining, max=limit,
                    message=f'行动值 {remaining}/{limit}，剩余 {remaining}。')

    def check(self, amount):
        limit = self._limit()
        remaining = self.state['remaining']
        enough = amount <= remaining
        message = (f'行动值足够：需要 {amount}，剩余 {remaining}/{limit}。' if enough
                   else f'行动值不足：需要 {amount}，剩余 {remaining}/{limit}。')
        return dict(ok=enough, amount=amount, remaining=remaining, max=limit, message=message)

    def spend(self, amount):
        limit = self._limit()
        remaining = self.state['remaining']
        if amount > remaining:
            return dict(ok=False, reason='insufficient', amount=amount, spent=0,
                        remaining=remaining, max=limit,
                        message=f'行动值不足：需要 {amount}，剩余 {remaining}/{limit}，未扣除。')
        self.state['remaining'] = remaining - amount
        return dict(ok=True, amount=amount, spent=amount, remaining=self.state['remaining'],
                    max=limit,
                    message=f'已扣除 {amount} 点，剩余 {self.state["remaining"]}/{limit}。')

    def _limit(self):
        return int(self.config.get('max', DEFAULT_MAX))

    def _moment(self, changed, limit):
        remaining = self.state['remaining']
        if changed:
            message = f'新时刻，行动值恢复为 {remaining}/{limit}。'
        else:
            message = f'重复时刻，行动值保持 {remaining}/{limit}。'
        return dict(changed=changed, remaining=remaining, max=limit, message=message)
