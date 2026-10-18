# 先锁、重查、操作、解锁

交易、赠送、移动会改多个节点，整体锁住所有执行模块或被修改的节点，再检查前提：
```python
try:
    async with ctx.network.lock_nodes([ctx.node_id, other], timeout=20):
        result = await ctx.network.call(other, '账户模块', 'read', {})
        if result['status'] != 'ok':
            raise RuntimeError(result['error'])
        # 锁内重查余额、库存、旧位置，检查后 await 完成修改。
except Exception as error:
    return ComponentResult(status='error', error=str(error))
return ComponentResult(data={'完成': True})
```
已有访问先结束，锁定节点仍可达，其他调用与信号等待。持锁者转调继承事务，频道强度不扩大。核心锁后备份状态、出边、发布资料、文档、Agent 输入和日志位置；正常退出提交，异常/取消恢复。

反例一：在 with 内 return error，属于正常退出，会提交！应让异常穿出锁作用域，在外面转 error。反例二：锁前检查位置，等到锁后直接改；前提可能已变，必须重查。

移动通常锁 NPC、旧地点、新地点；交易还包括执行库存模块的服务节点。不要锁整个网络。单次 patch_edges 保证边批次完整，不会包住余额和访客更新。

不要持锁等模型思考、独立信号、终端和外部网络。外部效果不能靠内部备份回滚；先提交待办，再做有幂等标识的外部动作，下次核对继续。嵌套锁只能重入已有集合，不能扩大。
