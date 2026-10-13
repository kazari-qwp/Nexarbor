# 原功能与成品组件对照

成品中的业务组件只使用工具、Skill、网络预设、工具箱、Agent 预设、节点六类。Harness 兼容代码独立放在已获准的适配层。

| 原功能/组件 | 拆分后类别 | 成品位置 | 依赖或接入方式 | 启停 ID |
|---|---|---|---|---|
| 图、接口、管理树、访问预算、委托及序列化 | 基础框架 | python/datanet/core | 标准库；通用应用事件、组件服务和检查点也归 Python 本体 | 保留基础协议 |
| Harness 会话、官方工具挂载、工具权限和文档历史 | Harness 适配层 | adapters/harness/framework | 原生 SDK；通过双向 RPC 执行 Python 返回的装配操作 | 宿主入口装配 |
| Harness 双向 RPC 及运行循环兼容 | Harness 适配层 | adapters/harness/backend；adapters/harness/runtime | 原生 AgentLoop；stdio 传输，检查点归 Python core | 插件补丁装配 |
| 建节点、建 Agent、建网络、管理接口和委托 | 工具 | components/tools/network_management | 节点及预设从清单发现 | tools/network_management |
| Agent 私有 Markdown 身份载体 | 基础框架 | python/datanet/core/agent_node.py | 固定原生 Agent 挂载类型；工具由网络管理组件提供 | 保留基础协议 |
| 拆链确认、离线文件夹、驻留释放和同根复用池 | 工具 | components/tools/agent_lifecycle | 图变更、原生 Agent 状态与委托事件 | tools/agent_lifecycle |
| 异步委托、持久 FIFO、等待和结果回送 | 工具 | components/tools/agent_delegation | 网络管理调用原生循环；队列独立保存 | tools/agent_delegation |
| 报告保存、UUIDv7 请求/委托索引及报告查询 | 工具 | components/tools/reports | 普通报告存储；委托事件开放查询入口 | tools/reports |
| 执行记录、异常记录和中断记录 | 工具 | components/tools/execution_records | 独立 JSON 状态；报告与经验使用可选端口 | tools/execution_records |
| 网络管理能力说明和指南 | Skill | components/skills/network_management | 依赖网络管理工具和声明的工具箱 | skills/network_management |
| 经验库、查询、候选经验及审核 | 工具箱 | components/toolboxes/experience | 独立持久库；Agent 能力事件装配 | toolboxes/experience |
| 排障、尝试上限、反馈、修复和普通退出 | 工具箱 | components/toolboxes/problem_handling | 经验、执行记录；真实反馈事件开放修复入口 | toolboxes/problem_handling |
| 管理树消息、插话、唤醒和一次性回复 | 工具箱 | components/toolboxes/agent_messaging | 管理关系与独立消息状态 | toolboxes/agent_messaging |
| 发现节点、读写、结构及暴露工具访问 | 工具箱 | components/toolboxes/network_access | 基础网络访问协议 | toolboxes/network_access |
| 节点本地读写工具装配 | 工具箱 | components/toolboxes/local_data | 节点协议及 NodeCodec；停用保留定义并拒绝执行 | toolboxes/local_data |
| 工程、官方工具、官方 Skill、只读和分工能力组合 | 工具箱 | components/toolboxes/*/box.json | includes、工具选项及 Skill 授权声明 | 按对应 toolboxes/<ID> |
| 项目根网络及固定项目资料 | 网络预设 | components/network_presets/project_root | 文本节点；根项目/进度/工作文件作为查询文本 | network_presets/project_root |
| 讨论黑板、轮次调度、成员及 Recorder 流程 | 网络预设 | components/network_presets/discussion_group | 文本节点、成员/Leader/Recorder 预设、网络工具 | network_presets/discussion_group |
| 数字网络、委托数字、实验分析及创建验证示例 | 网络预设 | components/network_presets/{number_network,delegated_number,experiment_analysis,creation_validation} | 相应节点与 Agent 预设 | 按对应 network_presets/<ID> |
| Worker、Operator、Coordinator、讨论及示例角色提示词 | Agent 预设 | components/agent_presets/* | 每个预设自己的提示词、默认工具箱和依赖 | 按对应 agent_presets/<ID> |
| 文本、常驻文本、查询文本、公共笔记及项目说明加载 | 节点 | components/nodes/text | 尾部由适配层 agent/request-tail 接入；查询正文进入历史 | nodes/text |
| 单值、CSV、SQLite、LlamaIndex 数据读写 | 节点 | components/nodes/{value,csv,sqlite,llamaindex} | 各自编解码、存储和可选第三方库 | 按对应 nodes/<ID> |

所有组件都由同目录 `component.json` 声明。`python scripts/components.py disable <ID>` 和 `enable <ID>` 修改 profile，重启 Harness 生效。关闭依赖项时依赖它的组件一起停用；恢复时仍尊重显式关闭的组件。组件数据保留，重新启用由原组件恢复。

## 本次源码迁移边界

原目录 `E:/harness-discussion-plugin` 和 `E:/数据库项目` 保留。新项目包含源码、六类组件、独立适配层和 Windows 后端，无运行时依赖原来的项目目录。构建时可以使用具有 PyInstaller 与节点依赖的 Python 环境。原生 Harness 模块由宿主提供。

## 实现归属

上表业务组件的应用运行入口统一在其 `python/datanet/features/.../runtime.py`，图服务在 `python/datanet/services/.../services.py`，节点实现和配置包在原 `python/datanet/components` 命名空间。工具静态定义位于组件根 `tools.json`。组件目录中不再保留 JavaScript 业务实现。
