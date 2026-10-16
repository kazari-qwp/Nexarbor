from datanet.world.model import *
from datanet.core.component_registry import resource_directory
import json
TOOLS=json.loads((resource_directory(__file__).parents[2]/"tools.json").read_text(encoding="utf-8"))

class Trade(ActionModule):
    module_name='world.trade';tools=TOOLS
    def apply(self,actor,name,args):
        a=person(self.backend,actor).state;item,n=args['item'],args['quantity'];stock=self.state['items'][item];price=stock['price']
        if item in ('axe','pickaxe') and (args['side']!='buy' or n!=1 or item in a['inventory']):raise ValueError('工具只能单件购买一次，坏工具可修理。')
        if args['side']=='buy':
            if stock['stock']<n:raise ValueError('商店库存不足。')
            take(a,'coins',price*n);stock['stock']-=n
            if item in ('axe','pickaxe'):a['inventory'][item]=5
            else:add(a,item,n)
        else:take(a,item,n);add(a,'coins',max(1,price-1)*n);stock['stock']+=n
        return dict(traded=True,item=item,quantity=n)
def register(s):s.node_module('world.trade',Trade)
