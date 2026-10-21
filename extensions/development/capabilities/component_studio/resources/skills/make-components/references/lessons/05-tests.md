# 用真实运行时验证

测试放 tests/test_*.py，使用 unittest；独立 pytest 函数不会被宿主运行。使用提供的夹具，不伪造 ctx：
```python
import unittest
from pathlib import Path
from datanet.studio.testing import ModuleHarness
class Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(Path(__file__).resolve().parents[1])
        self.h.add_node('a')
        self.h.mount('a', config={}, access={'strength':1,'channels':['demo']})
    async def asyncTearDown(self):
        await self.h.close()
    async def test_increment(self):
        result = await self.h.call('a','increment',{'amount':2},channels=['demo'])
        self.assertEqual(result['status'],'ok',result)
        self.assertEqual(result['data'],2)
```
这是标准计数器示例，请换成自己的操作、频道、配置和结果。夹具使用真实 NodeModules、图路径、工具路由和节点锁。依赖由宿主提供，h.mount(node,module='依赖ID',config=...,access=...) 后才可调用。

宿主的空节点预检只检查入口、装配、接收器声明与状态 Schema，不会在没有依赖和接线的节点上触发业务信号。声明接收信号的组件要在自己的完整夹具中用 h.emit 验证真实效果、失败和重复执行，不能把预检通过当作信号业务已通过。

夹具常用接口完整列表（不必通过 inspect/dir 或故意失败来猜）：
- `h.add_node(id,name=None,agent=False,description='')`，返回真实节点；Agent 必须 agent=True。
- `h.bind_agent(actor,binding)` 显式设置模块单测中的执行绑定，例如 `{'executor':'harness','strength':2,'channels':['turn','runtime.agent']}`；先 add_node(agent=True)，再绑定。它校验配置但不提供端口、装依赖或补权限。`h.register_agent(async_callback)` 只替换模型正文，回调 `(actor,message)` 返回字符串；端口提供与模块授权仍须显式声明。完整候选网络的绑定应本来就正确，用 NetworkHarness 验证，不在测试里补改。
- `h.add_text(id,text='',name=None)` 返回真实文本节点，node.file_path 可在测试中检查落盘内容。
- `h.connect(source,target,channels=['demo'],threshold=1,multiplier=1,attributes={})` 单向边，`h.disconnect(source,target)` 移除这对节点的所有出边。
- `h.mount(node,module=None,config=None,state=None,access=None)`，module省略表示当前被制作组件；依赖需另挂。返回真实实例，可在测试中检查 state。
- `await h.call(node,operation,parameters=None,actor=None,module=None,strength=2,channels=['demo'])`，返回 status/data/error。actor省略为本地调用。
- `await h.emit(actor,channels,strength=3,content=None)` 运行完整真实信号波，返回传播报告；源节点只是波的起点，不执行源接收器，接收器应装在出边目标上。
- `h.register_tools(provider,definitions,execute)` 注册测试宿主端口。definitions每项只有name/description/parameters，execute签名为async(actor,name,args)。还需 `node.offered_tools=[{'ref':'runtime:checkpoint','channels':['runtime.checkpoint']}]`；模块自身access也须授权频道。
- `h.register_readonly_ports()` 登记真实的 runtime:read_text，不伪造文件结果；offered_tools 与频道授权仍显式填写。详细契约见 nexarbor-basics 的 14-host-ports。
- `h.apply_context(actor, packet, source='prepare:test')` 用生产执行器的同一契约，把准备结果应用到真实 Agent 输入；用于验证四路形状、错误报告与事件重试。actor 应是 agent=True 的节点，不能只断言自己的组装返回字典看起来对。
- `h.network.nodes[id]` 是测试真实节点，出边列表是 `.interfaces`（每条有target_node_id/metadata）；Agent输入快照是 `.inputs.snapshot()`；没有network.edges或graph属性。
- 仅在测试中可用 `h.modules.factories['测试模块ID']=ModuleDefinition(execute,operations=[...])` 注册一个执行真实 ctx 调用或故障注入的测试模块，再h.mount装配它。实现文件不能用这些宿主对象。

add_node('b')、connect('a','b',channels=['demo'],threshold=1)，再 h.call(...,actor='a',strength=1,channels=['demo']) 测跨节点。断边、强度不足、错误频道要拒绝。h.tools.visit/invoke 测真实 Agent 工具。

检查正常、非法输入、重复和实例隔离；多节点操作注入末尾失败检查回滚，并发请求检查不超支。检查结果 status 和实际状态，不能只看信号封套收完。

有异步等待或共享外部资源时，安排两个操作真实重叠，检查资源操作是否按要求串行，不能把一次调用内部的顺序当成跨调用互斥。读取后还可能被替换的对象／版本，应检查旧读者迟到提交时如何处理，不能把旧意图默默套到新目标。自测预期也可能算错：按需求和初始数据独立核算，优先检查守恒量、重复无副作用及失败前后不变；修正错误预期应说明依据，不能删场景或改业务来迎合断言。

框架在进入 execute 之前就检查操作的 JSON Schema；类型错误会直接抛 jsonschema.exceptions.ValidationError，错误频道或不可达会抛 PermissionError。这是正常拒绝，不一定返回 ComponentResult。不要为了让测试收到错误封套而删除参数类型、required 或数值边界。示例：
```python
from jsonschema.exceptions import ValidationError
with self.assertRaises(ValidationError):
    await self.h.call('a','increment',{'amount':'假数字'},channels=['demo'])
```
组件自身检查的业务错误可以返回 status=error；多节点事务内必须先抛异常触发回滚，锁外再转成错误结果。

工具测试的真实形状如下，无需猜测或同时兼容好几种格式：
```python
entries = await self.h.tools.visit('a','a',strength=1,channels=['demo'])
entry = next(t for t in entries if t['tool_id']=='increment')
value = await self.h.tools.invoke('a',entry,{'amount':2},strength=1,channels=['demo'])
# invoke 返回公开操作的 data，出错抛异常；它不再包一层 status/data。
```

模块实现不能用夹具 backend；测试中才能查看测试节点。可按需研究标准样板，但测试预期应来自业务要求和接口契约，不能复制一套样板输出就宣称覆盖了自己的业务。宿主还有独立应用验收，不能删断言让测试通过。validate 通过且需求已覆盖就结束，不要无目的重复验证或继续润色。

不要留下故意无条件失败的探针测试；接口未知时查参考，能力缺口要报告。测试中的宿主故障注入与模块实现分开，不能把测试里可用的后端对象带进组件。

validate 默认返回状态、测试数量和失败位置。要追查完整栈时用返回的 job 调用 validate(job="编号",start_line=1,line_count=120)，按行读取，不重新运行。依赖目录提供接口和说明，源码用 read_resource 读取，不猜 dependencies 下存在 module.py。

验证默认时限60秒；确有较长整合流程可用 `validate(timeout_seconds=120)`，最多600秒，同任务后续自动验证沿用，仍受任务总时限限制。不要删有价值的场景来迎合过短时限。

需要验证当前应用里的完整消费链或真实存档重开时，可用 `from datanet.studio.network_testing import NetworkHarness`。`validate` 会提供隔离的当前网络、已发布依赖和此候选组件；`h=NetworkHarness()` 后可通过 `h.backend.modules.mount` 装候选，使用 `await h.call(actor,node,module,operation,parameters,channels=[...])`、`await h.emit(actor,channels,signal_id=...)`、`h.apply_context(actor,packet)`、`await h.restart()`，最终 `await h.close()`。详细 API 与用法见 nexarbor-basics 的 `references/lessons/15-behavior-tests.md`（工作副本 `lessons/15-behavior-tests.md`）。此夹具不运行真实模型或外部副作用。

自测的预期来自需求和使用方，不能仅验证自己选择的中间表示。接口有多个操作就分别调用；修改连接就检查后续真实读取；返回输入包就让真实消费方应用；声称恢复就关闭并重开实际存档。正常、重复、失败和一种新变体优先覆盖，未执行的部分如实列出。这样失败可先在自测中出现，而不依赖维护者逐条反馈。

测试一次默认参数入口，并在真实旧网络副本验证一次。不要只在自己特意搭配的新夹具里通过：既有连接未必带有你新发明的标签，既有配置也未必填了所有可选字段。迁移假设必须查看实际材料并验证，不能静默留下两套相互矛盾的结果。
