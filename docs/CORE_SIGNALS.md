# 核心信号与闭环脉冲

当前网络格式为 v8，连接保存为 `connections.interfaces`。核心负责通用传播，业务响应由节点所装模块声明。访问频道规则见 [频道与工具访问](CHANNEL_ACCESS.md)。

## 传播与汇总

信号携带来源、频道、强度、内容和稳定编号。频道决定哪些边可以通过，接口阈值检查当前强度；通过后乘边的 multiplier，同层到达目标的输入按该节点 aggregation 汇总，再加节点 divergence。结果为负不继续传播。

节点可选 sum、max、min、mean，默认 sum。汇总只针对当前广度层同时抵达的输入；同一信号对每个节点处理一次，不等待未来层回流。求和适合累加，最大值适合与参与人数无关的触发；改变人数时应一起检查闭环剩余强度。

广度逐层调度，同层异步并行，整层完成后再扩展下一层。只固定当前派发批次，下一层使用当前网络拓扑，因此模块移动或增删连接可影响后续传播。已经派发的处理仍按本次批次完成，不追溯撤销。

无处理器的节点中继。模块只响应其清单声明的信号频道，程序调用则显式选择模块和操作。接收者使用自己的授权，不能借发信者扩大访问范围。

## 发出与观察

```python
signal = Signal('source', ['tick'], 12, content={'task': '更新'},
                close_loop=True, failure_policy='continue')
receipt = runtime.emit(signal)
report = await runtime.wait(receipt['signal_id'])
```

emit 将传播任务与调用者的等待和取消范围分离。信号不会像函数调用那样把业务结果返回发起模块；wait 是宿主观察传播记录的接口。普通调用通过 `ctx.network.call` 返回 ComponentResult。

报告记录每层、各节点强度、来源路径和 processed/relay/failed 等状态。failure_policy=stop 时失败停止后续层，continue 时成功分支继续；部分失败不能当作全部成功。传播保留显式执行预算、超时和主动取消。

## PulseNode 与恢复

PulseNode 是有限闭环信号源，不认识时间或 NPC。只有显式连线回到源头、当前轮的工作完成并满足成功条件后，才开始下一轮；回源只登记 returned，不重复执行源处理器。闭环源与普通信号分开使用。

同一 signal_id、同一内容不会重放；复用编号但改内容会拒绝。中断记录恢复为 interrupted，宿主需确认外部副作用后再处理，不能无条件重放或承诺外部系统 exactly-once。

小镇的时间更新和每隔若干 tick 存档是项目模块，不属于信号核心。完整例子在 [内置小镇](../resources/examples/npc-town/)，可通过查看网络 Skill 沿 tick 频道研究。
