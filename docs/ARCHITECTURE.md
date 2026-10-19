# 核心、通信、前端三层

项目按运行职责分为三层，组件与应用通过登记的接口接入。三层不要求拥有同一种语言；公共文档格式位于 shared，是不执行服务的纯契约。

| 层 | 目录 | 职责与依赖 |
|---|---|---|
| 核心 | python/datanet/core/ | 节点、亚节点、归属、出边、频道与预算、信号、事务、模块运行、输入契约、序列化和检查点。只依赖标准库、核心及组件装配契约，不导入通信或前端实现。 |
| 通信 | python/datanet/communication/、communication/；adapters/harness/ 为具体宿主装配 | 通用双向 JSON-RPC、HTTP、浏览器请求和 iframe 桥；通过注入的处理函数转发请求。Harness 适配器接入执行器、项目服务和组件，负责实际生命周期。 |
| 前端 | frontends/network-editor/、frontends/desktop/ | 编辑、选择、渲染、面板与桌面窗口。编辑器经通信客户端请求服务，不读宿主文件或导入核心实现。桌面主进程是受信任装配入口，负责选择项目和启动宿主。 |

```text
编辑器 UI ─→ 浏览器请求客户端 ─→ HTTP 传输 ─→ 宿主路由 ─→ 核心与登记的组件
                                             │
                                    双向 JSON-RPC / 执行器端口
                                             │
                                        Harness 等宿主
```

## 阅读入口

- graph：network.py 负责寻路，ownership.py 负责归属与独立出边视图，channel_filters.py 负责过滤语义。
- module：local_modules.py 保留实例生命周期、回调范围和授权检查；module_requests.py 处理能力请求；module_queries.py 负责只读图/工具视图。值复制与调用上下文分别放在 module_values.py、module_scope.py，避免请求分发反向导入生命周期代码。
- execution：execution_binding.py 校验公共执行配置，execution.py 定义执行器协议。具体宿主校验自己支持的 executor；原生执行器不依赖制作工作室。
- wire：JsonRpcTransport 只管理消息、并发、反向回调、超时与关闭。backend/transport.py 和 studio/server.py 负责宿主操作。HTTP 传输只接收 request 函数；framework/editor-server.js 注入资源、聊天等服务。
- UI：main.jsx 组织页面，具体交互和显示位于各功能文件。通信细节集中在 communication/editor-client.js；shared/graph/ownership.js 供前端和磁盘预设共同判断单节点归属树。

现有公开 Network / NodeModules / Transport 入口与 v8 文件格式保持兼容。保留薄包装是为了不把目录整理扩散到所有组件，不复制实现。核心内部仍共享网络与模块运行状态，这是同一职责域的必要协作，不强行引入额外服务框架。

extensions/ 中的模块、数据节点与应用预设通过清单登记，Agent 执行统一由 DeepSeek Harness 原生宿主提供。组件使用核心公开端口，核心不写应用分支。组件选择见 [组件装配](COMPONENTS.md)，亚节点见 [归属与出边](SUBNODES.md)。

## 边界验证

这些回归文件保留在本地开发目录，由 Git 忽略，不随发布包分发。

tests/test_layer_boundaries.py 检查反向导入；tests/test_jsonrpc_transport.py 离线验证双向回调、关闭、超时与错误；前端 communication.test.js 用注入处理器直接验证传输。模块、信号、事务、上下文和真实客户端测试继续覆盖拆分后的行为。桌面 ZIP 装配包含 communication 和 shared，确保运行包中也有这些入口。

## 核心 Agent 节点

`AgentNode` 是核心类型，与普通 `Node`、`TextFileNode` 并列。它有稳定节点 ID、一份私人 Markdown 记忆，以及 `memory_read`、`memory_write` 两个私有工具。执行器可以绑定该节点，执行器种类和会话 ID 可随图保存；模型客户端、API 密钥与运行中的线程不序列化。

Agent 节点不内置协调者、讨论成员或执行组角色。这些角色由扩展节点配置及提示词装配。纯数据网络可以只创建普通节点和文本节点。

## 扩展包的四类组件

- `nodes/`：节点配置、Agent 角色配置、提示词与资源。
- `capabilities/`：工具、内部能力和事件服务的实现。业务 Python/JavaScript 只放这里；可声明模型可调用工具，也可只订阅事件。
- `toolboxes/`：工具 ID 列表及简短元数据。没有代码、嵌套工具箱或调度逻辑。
- `network_presets/`：网络拓扑、人数参数、资源引用与使用指南。

`component.json` 声明组件 ID、依赖、启停、资源和入口。能力可通过 `resources` 引用同扩展包里的节点、工具箱或网络预设资源。各工具箱的 `bindings.json` 定义工具 ID 对应的原生工具或扩展工具及授权配置，工具箱仅引用这些 ID。Skill 是能力提供的渐进式指南与授权入口，Agent 预设是节点配置。

未设置 `DATANET_COMPONENT_ROOT` 时，不加载协作包。启用方式：

```powershell
$env:PYTHONPATH = "$PWD/python"
$env:DATANET_COMPONENT_ROOT = "$PWD/extensions/multi_agent"
python scripts/components.py list
```

`extension.json` 选择组件及来源，依赖按拓扑顺序加载。`profile.json` 保存组件开关，`DATANET_COMPONENT_PROFILE` 可覆盖；明确停用依赖会阻止使用者运行，缺失、循环和版本冲突明确报错。停用能力会撤销其工具执行权限及上下文片段，持久数据保留。

## 执行器接口

核心 `ExecutionRequest` / `ExecutionResult` 与 `Executor` 协议定义 `run`、`cancel`、`status`、`send`。`ExecutorRegistry` 将 Agent 节点、会话和允许工具显式绑定，拒绝跨节点共享同一执行器会话及未登记工具。绑定可保存后恢复；恢复前应注册执行器并重新装配相应工具实现。

可选的 `MinimalExecutor` 接收外部模型客户端；`HTTPModelClient` 接受 OpenAI 风格的 chat-completions 端点，`MockExecutor` 用于离线测试。通过 `DATANET_EXECUTORS=["minimal"]` 挂载其命名空间。它是轻量参考循环，没有 Harness 的压缩、原生沙箱和完整会话管理。取消在模型返回及工具边界检查，无法强制打断任意阻塞的 Python 工具；宿主工具应自带超时或进程终止能力。

Harness 路径使用其原生循环。适配器的原生 Agent 句柄通过端口提供 create/run/inspect/steer/cancel 等操作；`adapters/harness/executor.py` 提供同一执行协议的外观，工具应先由原生注册表装配。

## 事件与宿主边界

| Harness 原生事件 | 通用事件或操作 |
|---|---|
| `agent/created` | 建立宿主连接，发出 `session/root`；扩展决定根网络和角色装配 |
| `agent/prepare-context` | `context/prepare` |
| `agent/request-tail` | `context/admitted` 与 `context/tail` |
| `agent/pre-step`、`agent/request` | 同名事件转发 |
| `tools/pre-execute`、`tools/result` | 执行许可检查、`tool/native-before` 与 `tool/result` |
| `agent/status`、`agent/error`、`agent/turn-stopping` | 同名事件转发 |
| `agent/inbox/discarded` | `message/discarded` |
| `agent/request-error` | 由可选 `response_recovery` 能力通过原生扩展入口订阅 |

适配器不选择协调策略或排障策略。`component-extension` 是通用原生扩展装配端口；纠错重试次数、终端执行上限、结束后清理等策略由能力拥有。扩展目录由 `extensionRoot` 显式传入；顶层协作插件入口选择 multi-agent 包，通用适配器默认不加载业务包。

## 上下文与持久化

固定职责进入原生系统提示；通道指南按需进入普通历史，压缩后按需再加载。工具采用 Harness 动态注册与 addition-only 定义，停用时拒绝执行。公共笔记及短状态仅进入请求尾部；查询文本按需读取。这些策略的业务触发条件由相应能力订阅事件实现。

图结构、节点资源与扩展状态由 Python 检查点保存；Harness 保存原生会话事件。可选执行器把自身历史保存到执行器目录。进程内运行不能任意时刻完整快照：恢复后如何处理未完成委托由队列能力决定，框架不会无条件重放具有副作用的操作。

历史组件机制保留；新项目使用 v3 模块和 v8 网络格式，应用迁移由宿主显式执行并先备份。

## 核心信号

接口统一为目标和元数据，信号携带不可变频道、内容与节点处理条件，按广度分层并行执行。核心PulseNode利用显式闭环和完成屏障产生有限轮次，不包含应用调度知识。当前网络序列化版本为 v8。API、通知语义、恢复和验证见[核心信号说明](CORE_SIGNALS.md)。
