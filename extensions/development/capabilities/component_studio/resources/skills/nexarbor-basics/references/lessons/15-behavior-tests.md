# 两种制作 Agent 共用的真实行为测试

`validate` 先静态校验候选，再在隔离进程中收集 `tests/test_*.py` 的 `unittest` 用例。没有行为用例只代表静态通过，不能作为制作完成。每个用例用一个新的 `NetworkHarness()`：网络制作取得当前候选，模块制作取得当前网络及候选组件；两者都包含已发布模块和受管理文件，建立独立真实 Backend。不要复制生产网络的固定快照到测试代码。

```python
import unittest
from datanet.studio.network_testing import NetworkHarness

class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = NetworkHarness()

    async def asyncTearDown(self):
        await self.h.close()

    async def test_example(self):
        result = await self.h.call('reader', 'ledger', 'records.store', 'read',
                                   strength=2, channels=['records'])
        self.assertEqual(result['status'], 'ok', result)
        self.assertIn('values', result['data'])
```

上面的 ID 只是例子，按自己候选的节点与公开接口填写。主要 API：

- `h.network.nodes`、`h.backend.modules`：隔离副本的真实节点对象、实例与运行时接口，供测试布置前提和核对结果。节点对象不是保存文件的字典；需要字典时用 `h.backend.snapshot()['network']['nodes']`。这里可以做故障注入，业务实现仍须使用 ctx。
- `await h.call(actor,node,module,operation,parameters=None,strength=2,channels=[])`：真实有向路由和模块授权。
- `await h.invoke(actor,target,ref,parameters=None,strength=2,channels=[])`：真实宿主端口路由；隔离图可实例化其声明的固定模板，具体声明见基础教程 16。
- `await h.run_pulse(pulse,cycles=1,timeout_seconds=15)`：从候选真实脉冲节点启动，保留原频道、强度及传播配置，默认断言全部轮次正常完成。未回源等失败立即报简短原因，完整报告在 `h.last_pulse_report`；明确验证失败时用 `expect_complete=False`。还要核对实际模块效果，并连续跑两轮，不能用手发信号替代后续真实入口。
- `await h.emit(actor,channels,strength=3,content=None,signal_id=None)`：底层信号专项入口；相同 signal_id 可测重复投递。不能用手填的频道和强度替代真实脉冲入口的验收。
- `h.apply_context(actor,packet,source='prepare:test')`：用正式执行器契约消费上下文准备包，检查事件、长期块和尾部块。只检查 packet 长得像字典不够。
- `await h.prepare_agent(actor)`：按候选原有执行绑定运行正式执行器的准备阶段，取得模型将看到的 system_prompt、context、inputs、tail、tools，发现 prepare 频道或工具来源接错；不调用模型、不代补执行配置。`await h.acknowledge_agent(actor,view['inputs'])` 模拟请求已消费这些事件，再准备或重开应不重发。
- `await h.restart()`：保存实际检查点、关闭并重开 Backend；再核对数据、事件确认和后续操作，不能用内存对象的深拷贝代替恢复。
- `h.register_agent(async_callback)`：只替换模型计算；回调 `(actor,message)` 返回回复正文字符串，可从 `h.last_agent_views[actor]` 核对正式模型输入。保留真实类型、绑定、准备、确认及同一 Agent 不可重入的约束；重开后替身保留。
- `await h.agent_tool(actor,name,arguments)`：像模型一样调用视图中的工具，经过正式执行器路由与授权。可在模型回调中用它执行发言、认领等真实协议，再返回正文；成功的模块工具直接返回业务 data，和 `h.call` 的 status/data 封套不同；宿主工具保留自身端口返回契约。不要直接改业务 state 或自己伪造协议结果。涉及多阶段自动唤醒时，用这种方式检查整条流程，而非在回调外手工逐步推动所有角色。
- `h.register_tools(provider,definitions,async_callback)`：其他确定性端口替身，仍经过 offer、授权和真实路由。已登记官方返回契约的端口会校验实际 envelope 与 value Schema，不能用任意字符串假装命令成功；按需查 catalog_ports 的精确 ref。不能覆盖 runtime:agent_run，用 register_agent。记录参数、调用方和次数，核对业务结果与幂等。

默认禁用真实模型、外部命令和不可逆副作用；只读文本、固定模板与检查点端口均运行于隔离副本。`runtime:checkpoint` 实际保存该副本，`h.restart()` 可验证关闭重开后的行为。付费模型、真实 Git 与外部系统另做端到端验收。端口不存在、模板未登记等环境缺口应明确报告，不能把失败当成功，也不能通过测试代码替正式产物补装必需配置。

先选正常流程、最可能的错误／重复／中断、再选一条跨组件完整流程。循环、多角色和重复运行写进测试一次执行，避免大量手工查询后漏掉回归。失败时读 `validate` 摘要定位，再按需分页展开原始日志；修复后从干净夹具重跑。不要为了通过而删接口、删断言或降低原需求。

分支单测可以隔离无关部分，但整体验收至少保留一次不剪边、不补配置的实际入口；每种角色和模板生成的 Agent 都要核对正式输入与工具。检查模板覆盖其宣称支持的参数，而非只测一个碰巧可用的默认值。跨异步等待还要测试两次操作交错、旧读后发生更新的情形；不要只验证单次顺序调用。

再做少量变换检查：组件装两份时，各自数据里的同名键仍应属于各自实例；两个实例引用同一共享资源时仍应识别为同一资源。预设放置会分配新编号，须检查配置引用和实际请求者身份仍能对应；`validate` 会提示疑似未声明的节点引用，但不会猜测或改写逻辑身份。还可增加并行路径、调整规模、重复投递，检查哪些结果应保持不变、哪些应随拓扑变化，不依赖自己选的特殊编号或额外标签。

大文档和批量数据优先把来源路径或引用交给模块，让代码解析、分批和校验；不要让模型把整份原文或全部记录转写进下一次工具参数。用接近公开真实规模的输入验证这条链路，核对完整内容、主键、精度和重复导入；只测试两行数组不能证明实际归档可用。

## 验收频道设计

按 `references/lessons/02-network.md` 的频道规范检查源码、实际调用轨迹和连线配置：

- 业务查询优先明确限定专有频道。发现先全频道遍历可达范围再筛目标的实现，应检查能否改成专有频道访问，不能仅凭结果正确就通过。
- 多条线若反复携带同样一组多个频道，应检查是否表达同一种关系、是否始终一起使用；可以合并就合并。保留冗余频道表必须有实际业务理由，不能只因为旧代码原来这样写。

这两项属于制作完成的验收标准。多条边复用一个合理的业务频道（如 `road`）符合规范；验收依据频道的实际作用，不按重复次数机械判错。网络查看工具仍可提供整体概览。

## 从使用者入口验收组合结果

先用简短表格对应原需求、实际入口、观察到的结果和未测缺口，不能因为已有很多用例就默认覆盖完整。组件各自通过不代表组合可用：从用户或模型真正拿到的工具走完一条流程，检查所有相关组件的终态；停止、退出、重试和再次运行也要维持同一套身份与状态，不能靠管理员额外补一步才成立。

用户要求可调的参数要逐个改变后实际运行，不能只改变其中一个，或把手工复制、改数组作为人数参数的替代。遇到实现限制先查对应能力教程，再决定组合或补缺口。生成对象要检查“具备所需功能”，不能只断言工具列表或上下文非空；不同配置分支至少各有一个实际消费检查。

读取源码、原始日志或测试结果页时，默认最多返回12000字符；长单行JSON也会分页。沿回执 `next_char` 用 `start_char` 续读同一文件或日志，必要时显式 `char_count`（最多20000）。先看失败摘要和相关位置，不因想看一个字段就逐页灌入整个网络或整份数据。
