# 商品商店

shop.market 装在地点，依赖本地 records.store 和 place.info。products 商品表记录 item、name、sale_price、buyback_price；空价格表示该方向不交易。inspect 查看商品与库存，buy / sell 按 item、quantity、key 交易。

短事务中重查资格、库存、金币和行动点，再统一交换；重复请求不重复扣费。价格和商品用配置区分，同类商店复用，不逐条编写金币和物品增减动作。具体限制与参数以 module.json 为准。
