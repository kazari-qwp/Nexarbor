# 可选 Python 执行器

只使用图与数据节点时不需要执行器。需要独立 Agent 循环时，在仓库根目录设置：

```powershell
$env:PYTHONPATH = "$PWD/python"
$env:DATANET_EXECUTORS = '["minimal"]'
```

最小离线运行：

```python
from pathlib import Path
from datanet.core.network import Network
from datanet.core.agent_node import AgentNode
from datanet.core.execution import ExecutorRegistry
from datanet.executors.minimal.runtime import MockExecutor

network = Network()
network.add_node(AgentNode("worker", "Worker", file_path="memory.md"))
executors = ExecutorRegistry(network)
executors.register("mock", MockExecutor(directory="sessions"))
executors.bind("worker", "mock", "worker-session", ["memory_read", "memory_write"])
print(executors.run("worker", "hello"))
```

实际模型使用 `MinimalExecutor(HTTPModelClient(base_url, api_key), model=model, directory=...)`。密钥由调用方提供，不写入图或执行器历史。工具由节点登记，再由绑定列表授权；不要将完整宿主工具集合默认授予模型。

`run` 支持 `prompt`、`max_steps`、`timeout_seconds`；执行器提供 `send`、`cancel`、`status`。同一会话只允许一个任务运行。取消在请求与工具边界检查，模型客户端受剩余时间约束；阻塞工具应自行设置超时。工具执行和完整结果写入会话历史，下一次运行继续使用该历史。

此执行器提供基础参考实现；Harness 路径使用 Harness 自己的循环、会话、压缩和工具执行。
