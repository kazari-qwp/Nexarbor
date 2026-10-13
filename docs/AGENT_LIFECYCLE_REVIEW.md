# 本次 Agent 文档与描述

以下链接指向实际加载给 Agent 的原文。提示词中仅调整个人笔记的名称和读写方式，职责沿用已有正文。

| 用途 | 文档 |
|---|---|
| 创建 Agent 节点 | [AGENTS.md](../components/tools/network_management/guides/datanet_create_agent/AGENTS.md) |
| 拆链确认、保存目录与重新连接 | [AGENTS.md](../components/tools/network_management/guides/datanet_interfaces/AGENTS.md) |
| 异步委托与结果等待 | [AGENTS.md](../components/tools/agent_delegation/AGENTS.md) |
| 网络管理总指南 | [AGENTS.md](../components/skills/network_management/resources/AGENTS.md)、[SKILL.md](../components/skills/network_management/resources/SKILL.md) |
| 小组预设指南 | [AGENTS.md](../components/network_presets/discussion_group/AGENTS.md) |
| 小组提示词 | [Leader](../components/agent_presets/leader/prompt.md)、[Recorder](../components/agent_presets/recorder/prompt.md)、[Member](../components/agent_presets/member/prompt.md) |
| 通用 Worker 提示词 | [prompt.md](../components/agent_presets/worker/prompt.md) |

## 工具描述原文

静态描述来源：[tools.json](../components/tools/network_management/tools.json)。对应通道入口沿用同一描述。

**datanet_create_agent**

```text
创建 Agent 节点，自动配备独立会话、个人记忆和读写工具；配置匹配时复用当前网络池中的 Agent。
```

**datanet_call_agent**

```text
向获准的下属 Agent 异步委托任务，立即返回委托 ID；同一 Agent 按提交顺序执行，结果由框架回送。
```

**datanet_interfaces**

```text
管理获准节点的链接；拆除导致节点与根断联时，确认取消、保存结构或分解进入复用池。
```

**datanet_presets**

```text
查看预设与已保存的离线网络；指定 ID 查看对应说明或保存清单。
```

动态描述来源：[网络管理 runtime.py](../components/tools/network_management/python/datanet/features/tools/network_management/runtime.py)、[异步委托 runtime.py](../components/tools/agent_delegation/python/datanet/features/tools/agent_delegation/runtime.py)。

**datanet_memory_read**

```text
读取自己的个人记忆文件。
```

**datanet_memory_write**

```text
更新自己的个人记忆文件；保留值得复用的经验和关键信息。
```

**datanet_wait_agent**

```text
等待或查看自己发起的委托，按委托 ID 返回执行结果。
```

## 拆链二级确认原文

```text
拆除链接将导致一部分节点和网络与根节点断开连接。
1. 取消拆除，保留该链接。
2. 拆除链接，从内存释放并保存到磁盘，保留结构。
3. 拆除链接并分解脱离部分，只保留 Agent 节点及其上下文、记忆文件，等待复用。
```

## 复用后首个委托前的提示

```text
你已被重新装配。管理者：<管理者 ID>。个人记忆和会话已保留，当前任务以新的委托为准。
```
