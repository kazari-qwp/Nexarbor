# 访问是一只手，信号是一道波

访问沿真实出边，受 access.strength/channels、边门槛/倍率与节点散度限制。参数 ID 只是数据，不授权。

## 频道设计：制作规范与验收标准

以下两条同时用于模块的业务访问设计和成品验收：

1. **优先沿专有频道访问。** 非常不建议先用全频道检索可达范围，再按节点名称、ID 或其他属性筛选目标。如果想这样做，优先考虑给想找的节点配置专有频道，沿该频道查询或调用，让网络直接表达访问关系。
2. **避免冗余频道表。** 频道不要过度冗余。除非迫不得已，应避免多条线反复携带同样一组多个频道；检查这些频道是否始终一起使用，能合并为一个表达该关系或任务的频道就合并。确需分开时，说明各频道承担的独立作用和不能合并的原因。多条道路都只用 `road` 一个频道，正符合这个原则。

验收时同时检查查询实际使用的频道和接线配置；能运行还不足以说明频道设计合理。网络查看工具的整体概览仍可按观察需求使用。

## 沿业务频道访问
```python
for node in await ctx.network.nodes(channels=['ledger']):
    if 'records.store' in node.modules:
        result = await node.call('records.store', 'read', {})
        if result['status'] != 'ok':
            raise RuntimeError(result['error'])
        account = result['data']
    for tool in node.tools:
        pass  # 直接收集这个节点的公开工具声明
```

`nodes()` 返回节点对象表，迭代顺序是去重的广度顺序，也可用已得到的 node_id 查表。遍历一次后，`node.metadata`、`node.tools`、`node.modules`、`node.edges` 直接读取该节点的本地表，不再寻路；`node.read(request)`、`node.write(key,value)` 和 `node.call(module,operation,args)` 直接操作已到达对象。无需把节点编号再交回 network 查询一次。模块的 config/state 可读副本和 operations 位于 `node.modules[模块ID]`，也可调用它的 `call(operation,args)`。

取得对象后的最小用法：
```python
nodes = await ctx.network.nodes(channels=['ledger'])
for node in nodes:                    # 已去重的 BFS 顺序
    tools = node.tools               # 本地公开工具表，不是另一个 await 查询
    if 'records.store' in node.modules:
        module = node.modules['records.store']
        config, state = module.config, module.state  # 可读副本
        result = await module.call('read', {})       # 同 node.call(...)
```

`nodes[node_id]` / `nodes.get(node_id)` 只查这次取得的表，整数下标和迭代保持 BFS 顺序。`node.path`、`node.strength` 是到达信息，不是下一次访问必须重新提交的凭证。节点对象属于当前有效回调，不能写进 JSON 参数、state 或持久配置；需要保留身份时保存节点 ID，下一次回调再按业务频道取对象。

普通文本用 `await node.read({'method':'key','key':'content'})`，返回 `status/items/sources/errors`，文本在 `items[0]['content']`。不需要配套模块，也不用向 Agent 暴露 read 工具。本地 `ctx.read/write` 仍同步作用于所在节点。

`await ctx.nodes` 使用本模块默认频道，并在当前回调内复用同一张对象表；需要特定业务范围时优先显式 `await ctx.network.nodes(channels=[专用频道])`。修改拓扑后要发现新对象，就再执行一次显式遍历；旧对象不会因每次访问而重新检查路径。不按节点 ID、名称或强度排序。收集器串联直接检查 `node.modules`，先调用下游组件，再读取当前节点工具表；用调用路径防环，按来源去重。

`ctx.network.call/read/tools/metadata/...` 仍是独立的网络请求，发起时会自行找目标；已经持有节点对象的循环不要再调用它们。被调模块使用自身装配授权，可继续转调；实际执行外部工具仍使用其公开调用入口。

频道表用 `ctx.filter_channels('配置字段', ['默认频道'])` 解析，它同时处理 `config.channel_modes[字段]` 的 allow/deny 并与当前授权相交。已有频道列表用 `ctx.resolve_channels(values, mode='allow')`。不要自己猜黑名单对应哪种参数，也不要给 nodes/read/call 传未声明的 channel_modes；它们接收的是解析后的 channels。接口形状以本文为准，不写多套 TypeError 回退去猜旧版本。

ctx.caller_id 是直接调用者，requester_id 是链条最初发起者，转调保留。替 NPC 移动或支付要核验 requester_id，不能相信参数里的 npc_id；身份也不代替路径。

edges(target) 返回出边副本。patch_edges([{source,target,action,metadata}]) 改边，action 为 add/remove，metadata 含 channels/threshold/multiplier/attributes。两端须可达，频道不能超过授权；remove 用完整原边精确匹配。批次先预检再整体改。业务还有其他修改则读 03。

信号用于独立传播，如 ctx.network.emit(channels=['tick'],strength=3,content={'day':1},kind='tick')。核心广度逐层，同层并行，整层等完才继续。signals 声明频道数组或 {'config':'signal_channels'}。响应时读 activation.signal.content/channels/kind，signal 不是字符串；已有 tick 沿网络走，不必每个节点再 emit。

反例：查全局状态或继承信号源所有权限。正确：每次经 ctx，参数表达需求，授权只可收窄。

信号处理失败需要抛异常，传播器才会把该分支标为失败、停止向后传播；ComponentResult(status='error') 是调用者读取的业务封套，信号传播器不会替业务解释它。成功信号仍返回ComponentResult。接收模块执行使用自己的access，不是signal.channels；例如收tick后可依自身授权调用本地runtime.checkpoint，无需改用信号源提供的工具或假设继承源权限。

节点 module_strength 是默认值，装配 access.strength:null 继承它；模块显式强度可更高，但每次请求仍只能收窄自身授权。它不是节点散度，也不是 Agent 执行器的强度。

在一条 tick 内需要后续回应，而发送者不能等待对方整轮执行时，用 ctx.network.post(target,module,operation,arguments,channels=[...])。它只在当前信号层可用，立即返回排队回执，本层等后续访问全部结束才进入下层；数量与时间有界。ctx.signal_id 给出当前层所属信号的标识，无信号时为 None。post 是新访问，不继承原事务或 requester_id，执行时重新检查路径和本模块授权。独立持续传播仍用 emit，不私自开后台任务。
