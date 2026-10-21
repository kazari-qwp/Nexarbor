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

本地回归检查反向导入、双向通信回调、关闭、超时和错误，并以注入处理器验证前端传输；模块、信号、事务、上下文和客户端检查覆盖分层后的行为。维护测试与运行记录不随源码发行内容和安装包发布。桌面 ZIP 包含 communication 和 shared，确保运行包中也有这些入口。

## 核心 Agent 节点

`AgentNode` 是核心类型，与普通 `Node`、`TextFileNode` 并列。它有稳定节点 ID、一份私人 Markdown 记忆，以及 `memory_read`、`memory_write` 两个私有工具。执行器可以绑定该节点，执行器种类和会话 ID 可随图保存；模型客户端、API 密钥与运行中的线程不序列化。

Agent 节点不内置协调者、讨论成员或执行组角色。这些角色由扩展节点配置及提示词装配。纯数据网络可以只创建普通节点和文本节点。

## 框架组件与应用项目

`extensions/development/extension.json` 选择框架通用组件，来源包括 foundation、composable、storage 和 knowledge_base。`component.json` 声明依赖、实现入口和资源；依赖按拓扑顺序加载。可用 `python scripts/components.py list` 检查选择，默认组件根是 `extensions/development`。

应用网络、业务模块、工具声明、数据及网络预设保存在 `projects/<项目>/`，内置标准教材在 `resources/examples/npc-town/`。宿主通过普通项目加载接口读取它们，不按应用名称注入规则或修补网络。`configs/` 的入口只存项目路径。项目装配使用 v3 模块与 v8 网络；模块经统一 `ctx` 访问数据、局部依赖和按频道可达的对象。

## 执行与上下文

核心定义执行协议及 Agent 绑定，Harness 适配器负责真实会话、模型连接、工具注册、取消和事件记录。API key 留在本机加密连接库，节点只保存连接引用；不随网络或 Git 版本发布。框架不包含独立模型执行循环。

上下文组装器按四类通道供给系统提示、普通上下文、一次性输入和每次更新的尾部块。文本沿配置频道收集，顺序服从广度遍历；准备操作显式登记在 Agent 执行绑定内。原生会话和核心检查点分别保存，恢复时不自动重复具有副作用的操作或一次性输入。

## 信号与调用

调用和信号都按频道、边乘数、节点偏置与接口阈值沿网络传播。调用由程序显式发起并把结果返回调用者；信号脱离发起者继续传播，不返回源头。信号广度逐层调度，同层异步并行；下一层依据当前拓扑继续传播。节点汇总模式为求和、最大值、最小值或平均值。锁只保护需要原子性的局部修改，不包住整个 Agent 活动。

## 预设与共享格式

预设的重复单元展开在核心完成；实例化的数据路径、prepare、工具来源及 Schema 中显式节点引用由 `shared/graph/subnets.js` 映射。客户端拖入和制作 Agent 的 `instantiate_preset` 使用同一实现。公共纯函数不依赖 DOM、文件系统或宿主运行时。
