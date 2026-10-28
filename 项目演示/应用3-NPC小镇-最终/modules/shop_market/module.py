"""商品买卖；双方库存、资金与业务收据共同提交或回滚。"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from app.runtime.requester import as_caller, requester_id
from domain.core import CallableTool, Module, access
from domain.json_values import thaw

TOOLS = json.loads(Path(__file__).with_name('tools.json').read_text(encoding='utf-8'))


async def call(participants,target,module,operation,args=None):
    return thaw(await getattr(participants[target].modules.get(module),operation)(**(args or {})))

async def trade(module,node,participants,operation,args):
    actor=requester_id.get()
    if not actor or participants[actor].node_type!='agent':raise ValueError('交易须由 Agent 发起')
    item=next((p for p in module.config.get('products',()) if p['item']==args['item']),None)
    if item is None:raise ValueError('该商品不在价目表中')
    quantity=args.get('quantity',1);price=item.get('sale_price' if operation=='buy' else 'buyback_price')
    if price is None:raise ValueError('商店不出售该商品' if operation=='buy' else '商店不回收该商品')
    signature=json.dumps([operation,args['item'],quantity],ensure_ascii=False)
    key=actor+'\x1f'+args['key']
    async with module.transaction([node.info.node_id,actor]):
        receipts=module.state.get('receipts',[])
        old=next((r for r in receipts if r['key']==key),None)
        if old:
            if old['signature']!=signature:raise ValueError('同一交易键不能改变商品、数量或方向')
            return dict(old['result'],duplicate=True)
        if (await call(participants,actor,'place.info','read'))['location']!=node.info.node_id:raise ValueError('请先到达商店')
        customer=(await call(participants,actor,'records.store','read'))['values'];stock=(await call(participants,node.info.node_id,'records.store','read'))['values']
        for field,expected in module.config.get('require_values',{}).items():
            if customer.get(field)!=expected:raise ValueError('不满足交易资格：'+field)
        cost=module.config.get('cost',1);total=quantity*price;currency=module.config.get('currency','coins');field=item['item']
        if customer.get('ap',0)<cost:raise ValueError('行动点不足')
        if operation=='buy':
            if stock.get(field,0)<quantity:raise ValueError('商品库存不足')
            if customer.get(currency,0)<total:raise ValueError('金币不足')
            delta={field:quantity,currency:-total,'ap':-cost};local={field:-quantity,currency:total}
        else:
            if customer.get(field,0)<quantity:raise ValueError('持有物品不足')
            if stock.get(currency,0)<total:raise ValueError('商店资金不足')
            delta={field:-quantity,currency:total,'ap':-cost};local={field:quantity,currency:-total}
        await call(participants,actor,'records.store','apply',{'deltas':delta})
        await call(participants,node.info.node_id,'records.store','apply',{'deltas':local})
        result=dict(operation=operation,item=field,quantity=quantity,total=total,duplicate=False)
        module.state['receipts']=(list(receipts)+[dict(key=key,signature=signature,result=result)])[-200:]
        return result


class ShopMarketModule(Module):
    def __init__(self, transaction, config=None, state=None, **access_settings):
        super().__init__('shop.market', **access_settings)
        self.transaction = transaction
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        for spec in TOOLS:
            self.tools._add(CallableTool(spec['id'], getattr(self, spec['operation']), spec['description'], deepcopy(spec['parameters'])))

    def _bind(self, node):
        super()._bind(node)
        source_id = sha256((node.info.node_id + '\0' + self.module_id).encode()).hexdigest()[:24]
        for tool, spec in zip(self.tools, TOOLS):
            tool.name = 'mod_' + sha256((source_id + '\0' + spec['id']).encode()).hexdigest()[:24]
            tool.description = node.info.node_id + ' · ' + spec['name'] + ' · ' + spec['description']

    @access()
    async def _participants(self, node):
        return node


    def _check_products(self):
        items = [product['item'] for product in self.config.get('products', ())]
        if len(items) != len(set(items)) or any(item in (self.config.get('currency','coins'), 'ap') for item in items):
            raise ValueError('商品不能重复或与货币、行动点字段同名')

    async def inspect(self):
        return next(iter((await self._inspect()).values()))

    @access(channels=())
    async def _inspect(self, node):
        self._check_products()
        values = (await node.modules.get('records.store').read())['values']
        return {'products':[dict(thaw(product), stock=values.get(product['item'],0)) for product in self.config.get('products', ())]}

    async def buy(self, item, quantity=1, key=None):
        return next(iter((await self._trade('buy',dict(item=item,quantity=quantity,key=key))).values()))

    async def sell(self, item, quantity=1, key=None):
        return next(iter((await self._trade('sell',dict(item=item,quantity=quantity,key=key))).values()))

    @access(channels=())
    async def _trade(self, node, operation, parameters):
        self._check_products()
        return await trade(self,node,await self._participants(),operation,parameters)
