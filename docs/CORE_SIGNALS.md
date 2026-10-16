# 核心信号、频道响应器与脉冲节点

当前网络格式为 **v5**。旧v3/v4网络和检查点直接拒绝，不做兼容转换。第一、第二应用尚未迁移；当前验证覆盖新核心、共享组件与NPC最小链路。

## 核心只负责传播

`Signal` 是不可变JSON值，携带来源、频道集合、内容、强度、方向、编号、父编号、序号、闭环标记、失败策略及执行预算。已删除 `NodeFilter`、`PermissionRequirement` 和 `activation`。

```python
signal = Signal('source', ['world.tick', 'notice'], 3,
                content={'task': '按当前目标活动'},
                close_loop=True, failure_policy='continue')
```

接口使用统一元数据：

```python
Interface('target', metadata={
    'visibility': 'public', 'threshold': 1, 'multiplier': 1,
    'channels': ['world.tick'], 'attributes': {'purpose': 'time'}
})
```

信号只能沿公有且频道有交集的接口传播，频道集合全程保持原样；强度按倍率及目标散度计算，不能低于0。私有数据访问仍遵守既有图权限，与信号传播分开。`wait_for_completion`及后台通知API已移除。

同一层的节点并行处理，每个节点等待自己的处理完成；整层完成后才能进入下一层。同一节点在一份信号中只处理一次，汇聚取最大强度而不相加。没有绑定处理器的节点直接中继，包括Agent节点；是否执行Agent由响应器决定。

`SignalRuntime.bind(node_id, async_handler, access_strength=...)` 是底层宿主接入接口，不负责业务匹配。接收者使用自己的宿主授权执行，不能借发信者权限。节点处理有互斥、期限和错误回执；`failure_policy='stop'` 停止后续层，`continue` 只让成功/中继分支继续。失败不能当作成功就绪。

## 节点信号响应器

`capabilities/signal_response` 是可选共享组件，配置保存在扩展状态，不增加核心节点字段。响应器由频道集合及有序工具步骤组成。到达节点后频道有交集就响应；同节点多个命中响应器按配置顺序执行。没有命中的响应器不执行工具，节点仍可中继。

```json
{
  "id": "live-this-moment",
  "channels": ["world.tick"],
  "steps": [
    {"tool": "match_prompts", "arguments": {}},
    {"tool": "run_agent", "arguments": {"task": {"$ref": "/signal/content/task"}}}
  ]
}
```

工具由宿主按节点显式绑定，不根据来信任意选择或扩大权限。参数支持JSON字面值和JSON Pointer引用：`/signal/...`、`/delivery/...`、`/steps/0/value/...`、`/responders/0/...`。没有eval、代码插值或任意函数查找。工具返回后才进入下一步；步骤失败停止当前节点后续步骤，并交由信号失败策略处理。同步工具在线程执行；超时后线程尚未结束时拒绝该节点重入。

装配示例：

```python
responses = app.plugins['capabilities/signal_response']
responses.bind(node_id, rules, {'match_prompts': match, 'run_agent': run}, access_strength=2)
```

异步工具接受 `(context, **arguments)` 并await；普通函数在线程调用，同样接受context。普通节点也可使用，无需Agent。配置可随Backend检查点保存，恢复后由宿主重新绑定可执行工具；不会自动重放中断的步骤。

## 提示词匹配器独立于信号

`capabilities/prompt_matching` 不导入信号模块。元数据统一通过核心 `Network.get_metadata` 读取，装配时只绑定文档来源；可以从响应器调用，也可单独调用。它通过已有 `load-document/document-present` 通道工作，不修改角色系统提示词。

文档以ID、正文/条件/投放方式的版本哈希作为标记。已有且仍在上下文中的文档不重复注入；首次、内容变更、压缩后标记消失时补充。`instructions`投放正文，`query`只提供文本节点入口。当前元数据或匹配集合变化时追加一条简短最新记录；版本号区分A→B→A，不能因旧A记录仍在就跳过新的状态通知。

匹配器保存的是当前适用集合及修订号，不是“已经加载”的永久标记。真正是否加载以原生会话投影或待入队文档为准；上下文标记丢失后重新加载。旧文本不从历史抹除，文档带条件，最新元数据记录说明当前条件与失配项。同一文档以最近注入版本为准。条件支持标准字段名或JSON Pointer，例如`/extensions/npc/role`；读取方不需要知道元数据扩展器是否存在。

## 节点元数据扩展器

`capabilities/node_metadata` 对普通、文本及Agent节点都适用。扩展字段按节点ID/命名空间保存在扩展检查点；不增加核心Node/Agent字段。`core`命名空间保留，不能覆盖。宿主可注册计算提供器读取业务状态，避免复制两份易失配的状态；附加字段不能覆盖提供器字段。

```python
metadata = app.plugins['capabilities/node_metadata']
metadata.set(node_id, 'custom', {'department': 'finance'})
metadata.register('runtime', lambda node_id: {'online': True})
network.get_metadata(node_id)  # 标准核心字段 + 可选extensions
network.nodes[node_id].get_metadata()  # 同一个统一入口
network.nodes[node_id].describe()  # 节点列表等现有操作也自动合并
```

核心MetadataRegistry负责统一读取：未装扩展器时只返回标准字段，装配后自动并入extensions。标准字段不能被扩展命名空间覆盖。Backend启动时注册扩展，无需先创建Application/Agent；恢复和拼图挂载继续使用同一读取入口。节点列表复用describe，因此不需要逐工具增加适配代码。

扩展命名空间默认只供节点自身、根与宿主读取，可通过注册提供器的public参数声明公开，统一读取仍遵守此可见性，避免把私人身份状态随节点列表泄露给其他节点。

NPC用`npc`命名空间提供性别、职业、孕期等字段。匹配器不导入元数据扩展器，只读统一核心接口。三个共享组件均可单独装配，没有NPC依赖，也没有相互强制依赖。

## PulseNode与持久化

核心PulseNode是有限闭环信号源，不认识时间、NPC或工具。`await pulse.run(runtime, cycles=2, timeout_seconds=180, cycle_complete=settle)`在本轮回源且整层结束后执行结算，再发下一份新信号。默认1轮；序号递增，parent_id关联上一份。回源仅记录returned，不再次执行源处理器或沿旧信号循环。

失败、未回源、超时、预算耗尽停止续发；只有显式allow_partial才接受部分完成。完整网络和信号记录可保存恢复；Backend自动接入检查点。相同signal_id相同内容不重放，不同内容拒绝。旧详情可压缩，去重身份保留。处理中恢复标为interrupted，需要宿主核实副作用再reconcile，不能保证跨外部系统exactly-once。

## 最小验证

核心20项、共享组件6项、NPC9项通过；另有原生Harness+Mock和历史文档标记测试。没有付费调用，也没有运行全世界真实Agent。第一、第二应用未迁移，不以旧应用结果宣称兼容v5。

新增工具描述原文：`按自己的身份元数据补充尚未加载的提示文档。` NPC响应器内部调用该工具，不默认暴露给NPC模型。
