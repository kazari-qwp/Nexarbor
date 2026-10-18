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

add_node('b')、connect('a','b',channels=['demo'],threshold=1)，再 h.call(...,actor='a',strength=1,channels=['demo']) 测跨节点。断边、强度不足、错误频道要拒绝。h.tools.visit/invoke 测真实 Agent 工具。

检查正常、非法输入、重复和实例隔离；多节点操作注入末尾失败检查回滚，并发请求检查不超支。检查结果 status 和实际状态，不能只看信号封套收完。

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

模块实现不能用夹具 backend；测试中才能查看测试节点。不读取项目现成业务答案。宿主还有独立应用验收，不能删断言让测试通过。validate 通过且需求已覆盖就结束，不要无目的重复验证或继续润色。
