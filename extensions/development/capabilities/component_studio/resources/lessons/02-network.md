# 访问是一只手，信号是一道波

访问沿真实出边，受 access.strength/channels、边门槛/倍率与节点散度限制。参数 ID 只是数据，不授权。
```python
nearby = await ctx.network.nodes()
result = await ctx.network.call('可达节点', '模块ID', 'read', {})
if result['status'] != 'ok':
    raise RuntimeError(result['error'])
data = result['data']
```
nodes 返回 metadata/path/strength。nodes、metadata、tools、visit、tool_sources、edges 查询都要 await。call/invoke 一调用就启动独立任务；依次 await 表达顺序。被调模块使用自身授权，可继续转调。同节点不花跳数，频道仍须匹配。

ctx.caller_id 是直接调用者，requester_id 是链条最初发起者，转调保留。替 NPC 移动或支付要核验 requester_id，不能相信参数里的 npc_id；身份也不代替路径。

edges(target) 返回出边副本。patch_edges([{source,target,action,metadata}]) 改边，action 为 add/remove，metadata 含 channels/threshold/multiplier/attributes。两端须可达，频道不能超过授权；remove 用完整原边精确匹配。批次先预检再整体改。业务还有其他修改则读 03。

信号用于独立传播，如 ctx.network.emit(channels=['tick'],strength=3,content={'day':1},kind='tick')。核心广度逐层，同层并行，整层等完才继续。signals 声明频道数组或 {'config':'signal_channels'}。响应时读 activation.signal.content/channels/kind，signal 不是字符串；已有 tick 沿网络走，不必每个节点再 emit。

反例：查全局状态或继承信号源所有权限。正确：每次经 ctx，参数表达需求，授权只可收窄。

信号处理失败需要抛异常，传播器才会把该分支标为失败、停止向后传播；ComponentResult(status='error') 是调用者读取的业务封套，信号传播器不会替业务解释它。成功信号仍返回ComponentResult。接收模块执行使用自己的access，不是signal.channels；例如收tick后可依自身授权调用本地runtime.checkpoint，无需改用信号源提供的工具或假设继承源权限。
