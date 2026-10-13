# 本次最小验证

本次使用源码后端、重新构建的 Windows 后端和本机 Harness 0.2.0-rc.2 的原生 SDK。模型请求由本地 MockAdapter 返回，不消耗付费 API。

| 验证 | 结果 |
|---|---|
| 所选根预设因依赖关闭时，空网络仍可启动 | 通过 |
| 显式启用的依赖组件随关闭的依赖项停用，运行时钩子回收 | 通过 |
| Python 本体独立加载节点与工具箱，未导入 Harness 适配层 | 通过 |
| 讨论、排障组件关闭后重新开启，任务与反馈恢复 | 通过 |
| 文本和单值节点组件关闭后数据可保存，重新开启可读取 | 通过 |
| 常驻/查询文本、多项目说明、根查询文档 | 通过 |
| 原生反馈事件首次开放修复入口，重复装配不重复添加钩子 | 通过 |
| 委托事件开放报告查询，指南按历史去重 | 通过 |
| 成员没有主动发送工具，收到消息后只可回复一次 | 通过 |
| 关闭组件后停用旧工具，并移除公共笔记尾部钩子 | 通过 |
| 原生模型请求只有最新公共笔记，历史不残留旧正文 | 通过 |
| 压缩后查询文档按需重新加载；停用工具保留定义并拒绝执行 | 通过 |
| 原生插件补丁只有一个有效 AgentLoop 和对应 invariant | 通过 |
| 替换运行时继承原配置式 Agent 和并行工具上限 | 通过 |
| 节点工具箱在恢复流程中停用拒绝执行、保留定义与数据、恢复可写 | 通过 |
| 原生 AgentRegistry 创建普通 Agent 与五个讨论成员，各有独立上下文和 Session | 通过 |
| 报告组件关闭后执行记录仍可开始和正常结束 | 通过 |
| 新构建可执行文件：RPC、项目根、多查询文本小组装配 | 通过 |

没有运行完整讨论任务、付费模型测试或客户端界面验收。客户端加载与模型缓存表现需要后续真实客户端任务验证。

## 可复现入口

- `tests/component-runtime.test.js`：依赖开关与运行时卸载。
- `tests/component-runtime.test.js`：依赖开关与运行时卸载。
- `tests/test_components.py`：本体独立性、关闭/恢复、节点工具箱停用和后端二进制。
- `tests/test_shared_texts.py`：文本模式、项目来源与 Recorder 写入。
- `tests/modular-plugin-test.cjs`：组件原生事件、权限与可选端口。
- `tests/modular_creation_test.cjs`：原生 AgentRegistry 独立会话装配。
- `tests/modular_shared_runtime_test.cjs`：原生 AgentLoop 请求尾部、历史及权限。
- `tests/modular_shared_loader_test.cjs`：原生插件补丁。
- `tests/modular_adapter_test.cjs`：原配置式 Agent 与并行工具配置继承。

Python 测试使用已安装 pandas 等节点依赖的解释器。设置 `DATANET_TEST_BINARY=1` 后可单独运行 binary_rpc 用例。JavaScript 测试需要本机 Harness 原生 SDK，默认从 LOCALAPPDATA 下的安装目录查找，也可设置 `DATANET_NATIVE_MODULES`。

原生 Electron 入口执行：`ELECTRON_RUN_AS_NODE=1`，随后用 Harness 可执行文件加 `--experimental-vm-modules tests/<测试文件>.cjs`。测试临时数据默认在成品的 build/test-data，可以设置 DATANET_TEST_TEMP。

组件事件与创建测试替换了官方工具挂载，并使用本地会话 flush；它们验证生命周期和会话装配。请求尾部测试使用原生运行循环和 MockAdapter。官方工具的真实权限弹窗和客户端窗口展示未在本次重新验收。
