"""Generic persisted period budget; mutations join the caller's transaction."""
from copy import deepcopy
from datanet.core.node_modules import NodeModule
from datanet.core.json_values import freeze

class ActionBudget(NodeModule):
    def install(self):
        capacity=self.config.get('capacity')
        if type(capacity) is not int or capacity<1:raise ValueError('Budget capacity must be a positive integer')
        costs=self.config.get('costs',{})
        if not isinstance(costs,dict) or any(not isinstance(k,str) or not k for k in costs):raise ValueError('Costs require named operations')
        if any(type(v) is not int or v<0 for v in [self.config.get('default_cost',1),*costs.values()]):raise ValueError('Costs must be nonnegative integers')
        self.state.setdefault('period',None);self.state.setdefault('spent',0)
        if type(self.state['spent']) is not int or not 0<=self.state['spent']<=capacity:raise ValueError('Invalid saved budget')
    def guard(self):
        if not self.active or (self.owner and self.owner not in self.backend.components.enabled):raise PermissionError('Action budget is inactive')
    def status(self,context=None,*,period):
        self.guard();freeze(period)
        if period is None:raise ValueError('A non-null period ID is required')
        with self.backend._transaction_lock:
            capacity=self.config['capacity'];spent=self.state['spent'] if self.state['period']==period else 0
            return dict(period=deepcopy(period),capacity=capacity,spent=spent,remaining=capacity-spent)
    def check(self,context=None,*,action,period):
        if not isinstance(action,str) or not action:raise ValueError('Action name is required')
        with self.backend._transaction_lock:
            status=self.status(period=period);cost=self.config.get('costs',{}).get(action,self.config.get('default_cost',1))
            if cost>status['remaining']:raise ValueError(f"行动值不足：需要{cost}，剩余{status['remaining']}/{status['capacity']}。本次未执行。")
            return dict(cost=cost,**status)
    def charge(self,context=None,*,action,period):
        with self.backend._transaction_lock:
            quote=self.check(action=action,period=period)
            self.state.update(period=deepcopy(period),spent=quote['spent']+quote['cost'])
            return dict(cost=quote['cost'],**self.status(period=period))

def register(s):s.node_module('action.budget',ActionBudget)
