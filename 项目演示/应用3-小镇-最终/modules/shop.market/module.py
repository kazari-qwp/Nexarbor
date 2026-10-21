"""商品表统一买卖：库存、资金和客户记录在一个节点事务中交换。"""
import json
from datanet.core.module_protocol import ComponentResult
from datanet.core.json_values import thaw

async def call(ctx,target,module,op,args=None):
    result=await (await ctx.nodes)[target].call(module, op, args or {})
    if result['status']!='ok':raise ValueError(result.get('error') or '商店操作失败')
    return thaw(result['data'])

async def trade(ctx,operation,args):
    actor=ctx.requester_id
    if not actor or ((await ctx.nodes)[actor].metadata)['node_type']!='agent':raise ValueError('交易须由 Agent 发起')
    item=next((p for p in ctx.config.get('products',()) if p['item']==args['item']),None)
    if item is None:raise ValueError('该商品不在价目表中')
    quantity=args.get('quantity',1);price=item.get('sale_price' if operation=='buy' else 'buyback_price')
    if price is None:raise ValueError('商店不出售该商品' if operation=='buy' else '商店不回收该商品')
    signature=json.dumps([operation,args['item'],quantity],ensure_ascii=False)
    key=actor+'\x1f'+args['key']
    async with ctx.network.lock_nodes([ctx.node_id,actor]):
        receipts=ctx.state.get('receipts',[])
        old=next((r for r in receipts if r['key']==key),None)
        if old:
            if old['signature']!=signature:raise ValueError('同一交易键不能改变商品、数量或方向')
            return dict(old['result'],duplicate=True)
        if (await call(ctx,actor,'place.info','read'))['location']!=ctx.node_id:raise ValueError('请先到达商店')
        customer=(await call(ctx,actor,'records.store','read'))['values'];stock=(await call(ctx,ctx.node_id,'records.store','read'))['values']
        for field,expected in ctx.config.get('require_values',{}).items():
            if customer.get(field)!=expected:raise ValueError('不满足交易资格：'+field)
        cost=ctx.config.get('cost',1);total=quantity*price;currency=ctx.config.get('currency','coins');field=item['item']
        if customer.get('ap',0)<cost:raise ValueError('行动点不足')
        if operation=='buy':
            if stock.get(field,0)<quantity:raise ValueError('商品库存不足')
            if customer.get(currency,0)<total:raise ValueError('金币不足')
            delta={field:quantity,currency:-total,'ap':-cost};local={field:-quantity,currency:total}
        else:
            if customer.get(field,0)<quantity:raise ValueError('持有物品不足')
            if stock.get(currency,0)<total:raise ValueError('商店资金不足')
            delta={field:-quantity,currency:total,'ap':-cost};local={field:quantity,currency:-total}
        await call(ctx,actor,'records.store','apply',{'deltas':delta})
        await call(ctx,ctx.node_id,'records.store','apply',{'deltas':local})
        result=dict(operation=operation,item=field,quantity=quantity,total=total,duplicate=False)
        ctx.state['receipts']=(list(receipts)+[dict(key=key,signature=signature,result=result)])[-200:]
        return result

async def execute(ctx,activation):
    try:
        items=[p['item'] for p in ctx.config.get('products',())]
        if len(items)!=len(set(items)) or any(item in (ctx.config.get('currency','coins'),'ap') for item in items):raise ValueError('商品不能重复或与货币、行动点字段同名')
        if activation.operation=='inspect':
            values=(await call(ctx,ctx.node_id,'records.store','read'))['values']
            return ComponentResult(data={'products':[dict(thaw(p),stock=values.get(p['item'],0)) for p in ctx.config.get('products',())]})
        return ComponentResult(data=await trade(ctx,activation.operation,activation.parameters))
    except Exception as error:return ComponentResult(status='error',error=str(error))
