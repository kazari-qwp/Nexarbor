# 访问是一只手，信号是一道波

访问沿真实出边，受装饰器的频道/强度、边门槛/倍率与节点偏置限制。参数 ID 只是数据，不授权。

## 频道设计：制作规范与验收标准

以下两条同时用于模块设计和成品验收：

1. **优先沿专有频道访问。** 非常不建议先全频道遍历，再按名称、ID 或其他属性筛目标；优先通过专有频道与真实连接表达访问关系。
2. **避免冗余频道表。** 多条线反复携带同一组频道时，检查是否始终一起使用；能合并为一种关系或任务就合并。确需分开时保留独立作用。多条道路只用 road 正符合此原则。

验收同时检查实际查询频道和接线；网络查看工具可按观察需要显示整体。

## 沿业务频道访问
```python
@access(channels=['ledger'], strength=2)
async def read_accounts(self, node):
    module = node.modules.get('records.store')
    if module is not None:
        return await module.read()
```
模块只编写对单个节点的操作。装饰器从所属节点出发，去重、广度逐层推进，同层异步并行、整层结束后再向外；结果为 {node_id:回调结果}，顺序保持实际遍历顺序。不按名称、ID 或强度重排，也不再拿到达编号重复寻路。

回调内直接用 node.info、node.modules、node.tools、node.links。模块用 node.modules.get(id)，直接调用其公开方法；工具箱是可迭代 Tools，需要列表就 list(node.tools)，调用单个工具用 tool.invoke(**arguments)，异步结果再 await。无需 list/invoke 提供器或兼容旧封套。

显式装饰器参数优先；无参数 @access() 使用模块的 channels/strength/channel_mode，没有频道设置则只在本节点执行一次。需要明确本地操作用 @access(channels=())。频道匹配用 channel_mode='allow' 或 'deny'，无需旧的频道解析接口。

节点对象属于当前回调，不写入 JSON 参数、state 或持久配置。保留身份用 node.info.node_id，下次行为重新通过装饰器访问。需要在结果上汇总时，由公开方法处理返回字典的 values，不在模块中再实现一套遍历。

调用链原始身份用 app.runtime.requester.requester_id；转调保留该身份。替 NPC 移动或支付不能相信参数里的 npc_id，身份也不代替路径。

出边在 node.links；用 Link(target_id,channels,threshold,processor=Multiplier(factor),channel_mode=...) 表达连接。修改涉及多个节点或其他业务状态时读03，锁内重查后只修改已到达节点的实际表。不恢复同归属树无连线调用。

信号由注入的 emit 运行端口独立发起，不复用 access。处理器为 async on_signal(self,context)，读取 context.signal 的 content/channels/kind。已有 tick 沿网络推进，不必每个节点再 emit，传播机制见10。

需要同层后续回应时，使用 app.runtime.signal_work.current_work 中当前层的 post，提交一个通过 access 访问的异步函数；立即取得排队回执，本层等待它完成再推进。后续工作不继承原事务或调用身份；独立持续传播仍用 emit，不私开后台任务。

反例：查询全局网络、把已到达对象交回旧路由、继承信号源全部权限。正确：跨节点行为只通过装饰器，取得对象后直接使用。
