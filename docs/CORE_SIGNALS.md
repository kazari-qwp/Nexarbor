# 核心信号与脉冲节点

2026-10-16：直接升级核心，网络格式为 **v4**。本轮不迁移应用配置，不接受v3网络文件或旧版Interface构造参数。第一、第二应用保持原样；现有NPC预设也尚未改装为脉冲网络。旧应用的验证记录对应此前提交，不能作为新核心的兼容性结论。

## 接口结构

```python
Interface('receiver', metadata={
    'visibility': 'public',
    'threshold': 1,
    'multiplier': 1,
    'channels': ['world.tick', 'request.collect'],
    'wait_for_completion': True,
    'attributes': {'example.purpose': 'schedule'},
})
```

接口只有目标和不可变元数据。公私、门槛、倍率、频道及等待策略都在metadata中；attributes容纳组件的额外JSON属性。所有字段有结构/类型校验，未知内置字段报错。元数据不能修改已有实例，需要创建替代接口。

- 信号和接口频道均为去重集合，名称由组件声明，不是核心枚举。
- 频道有任意交集即可通过，**信号频道原样保留**。携带A、B的信号可以先过A接口，再过B接口。
- 信号只沿所选方向上的公有连接传播。私有连接仍按原规则服务所属节点的数据访问，不参与信号传播。
- 空接口频道不承载信号；空信号频道拒绝创建。不存在隐式通配符。
- 倍率、门槛和目标散度共同决定剩余强度。信号不投递到剩余强度为负的节点；0强度仍可被接收，能否继续由下一条边和目标散度决定。

## 信号对象

```python
from datanet.core.signals import Signal, NodeFilter, PermissionRequirement
signal = Signal(
    origin='requester',
    channels=['request.collect'],
    strength=3,
    content={'request': '收集你掌握的信息', 'target': 'shared/report'},
    activation=NodeFilter(
        types=['agent'],
        required_tools=['node_invoke'],
        permissions=[PermissionRequirement('shared/report', 'write', 'write')],
    ),
    max_hops=8,
    max_deliveries=100,
    timeout_seconds=120,
    node_timeout_seconds=60,
)
```

Signal为不可变JSON值，含唯一编号、真实来源、频道、内容、激活条件、方向、强度、失败策略和执行预算。NodeFilter的各组条件之间为AND；types和node_ids组内为OR；required_tools及permissions要求全部满足。节点类型支持核心类型类别和已注册codec类型ID。过滤未命中不调用处理器，但仍可中继信号。

工具集合由宿主绑定提供，可用函数动态读取当前授权。目标权限默认通过接收者自己的访问预算检查图可达和目标公开工具方向，也可以由宿主提供更细的permission_checker。筛选只决定是否激活，实际工具执行继续接受原有权限检查。信号既不能伪造发起者，也不能通过频道或节点条件扩大工具授权。

## 广度执行

```python
runtime = network.signals
async def process(context):
    # context.signal：原始信号；context.delivery：本次路径、强度、层级和父节点。
    # context.receipt_id：signal_id + node_id，可用作业务幂等键。
    return {'processed': context.signal.signal_id}

runtime.bind('receiver', process, capabilities=['node_invoke'], access_strength=2)
report = await network.propagate(signal)
```

每一层并行执行，收齐本层需要完成的处理后，再沿其接口计算下一层。普通无处理器节点可以中继；匹配激活条件的Agent必须绑定宿主处理器，否则记录失败，不假装已经工作。处理器必须是异步函数或返回可等待对象，实际接收者身份和自身授权预算进入上下文，之后恢复原上下文。

同一个信号每个节点只处理一次。多条路径汇聚时合并父节点，采用**最强输入而非求和**，避免多人回源放大强度。同层多路到达只调用一次处理器。每次信号开始冻结节点集合、接口和散度；中途变更拓扑从下一信号开始生效。

`wait_for_completion=False` 是终端通知订阅：后台投递、不阻挡主传播屏障，**不承担后续信号中继**。需要“先处理、再转发”的连接必须设True。后台通知可以显式调用 `drain_notifications(signal_id)` 等待，或 `cancel_notifications(signal_id)` 取消；宿主结束前调用 `await runtime.close()` 清理。失败策略只针对需要完成的分支，通知失败仍记入相应回执。

`failure_policy='stop'` 在本层失败/超时后停止后续传播；`continue` 让成功分支继续，最终结果标为partial。超时、取消、跳数和投递数均有记录。Asyncio取消是协作式的，不能强杀任意Python代码；处理器和宿主外部工具必须遵守取消契约。

## Agent处理完成即就绪

核心提供 `ExecutorRegistry.bind_signals(runtime, node_id)`，把已装配的执行器接到信号处理器。正常执行完成就是本节点完成，无需模型调用ready或submit工具。

同步执行器通过线程运行并使用原有取消接口；如果取消请求返回后旧线程仍未结束，该Agent会阻止启动新的信号任务，直到旧线程真正退出。框架不把“已请求取消”当成“执行已经停止”。Harness可通过 `runtime.bind` 接入自己的原生异步run/whenIdle回调；本轮未修改其适配层或应用装配。

## 核心PulseNode

```python
pulse = PulseNode('pulse', 'Clock source', channels=['world.tick'], strength=3)
network.add_node(pulse)

# 预先装配 pulse -> clock -> agents -> pulse 的同频道公有接口。
async def settle(pulse, report):
    # 通用轮次结束钩子，业务在组件中结算，完成后才允许下一次发出。
    pass

result = await pulse.run(network.signals, cycles=2,
                         timeout_seconds=180, cycle_complete=settle)
```

PulseNode是核心第四种节点类型，与node、text_file、agent并列。没有内置模型可调用工具，不认识NPC、日期、家庭或地图。

脉冲源发出新Signal；允许同一信号一次返回源头。回源只记录闭环，不再次处理源、不再沿旧信号继续循环。整个必需传播完成且闭环成功后，先执行cycle_complete，再以新编号和新的visited发下一次；新信号保留parent_id和递增sequence。发射强度采用脉冲源明确配置的新预算，不从回源汇聚中创造预算。

默认只运行1轮，必须提供有限的cycles和总时限。没有回源、必需分支失败、超时或预算耗尽会停止续发。partial结果只有显式allow_partial=True才允许继续。新增节点在下一轮拓扑快照中进入。

## 保存、恢复与去重

纯Network可用save_network/load_network保存配置和执行记录。`backend.signals` 自动接入现有检查点，在信号开始、层完成和脉冲阶段边界保存状态；长时间等待处理不持有图事务锁。

相同signal_id及相同内容返回已有结果，不重复处理；相同编号不同内容拒绝。只压缩旧记录详情，不删除去重身份；压缩后的结果带compacted标记。历史详情默认保留最近100份，其余保留信号身份与状态，因此去重索引仍会随独立信号数量增长。

回调、线程、原生会话句柄不序列化。运行中信号和脉冲恢复后标为interrupted，拒绝自动重放；宿主需先核实副作用。PulseNode.reconcile(reason) 是宿主明确记录已核实状态后，允许新一轮的入口；不是继续执行旧信号。回调内部的业务事务、外部写入和模型请求无法仅靠信号日志实现跨系统exactly-once，组件可使用receipt_id做幂等。

## 本轮验证

```powershell
$env:PYTHONPATH="$PWD/python;$PWD/tests"
$env:DATANET_COMPONENT_ROOT="$PWD/extensions/.none"
.venv/Scripts/python.exe -m unittest test_core_signals -v
.venv/Scripts/python.exe scripts/demo_core_pulse.py
```

19项新核心测试及1项现有纯核心装配测试通过；纯核心示例执行2轮：两个Agent第一轮都读到第1天-早，第二轮都读到第1天-午，且每轮完成汇聚后才开始下一轮；保存恢复后脉冲序号为2。全部离线，无付费API、无真实NPC全世界运行。旧应用兼容性测试未作为本轮目标。

Agent可见的新增节点描述原文：**脉冲节点：按频道发出有限轮次信号，闭环返回并完成本轮处理后继续下一轮。** 原有Agent提示词和应用指南未修改。
