# 本次验证

当前版本 0.3.4 的验证覆盖 Agent 节点、离线归档、复用、内存驻留、持久队列、双向通信和最终 Windows 后端。原生 Harness SDK 使用本机 0.2.0-rc.2，模型由本地模拟响应提供，无付费 API 调用。以下未标注本次的适配补丁验证沿用重构阶段记录。

| 入口 | 本次结果与覆盖 |
|---|---|
| `tests/test_components.py` | 5 项源码测试通过：Python 本体独立、组件关闭/恢复、数据保留、本地工具箱撤权；二进制用例另行运行 |
| `tests/test_shared_texts.py` | 3 项通过：常驻/查询文本、多个项目来源、根查询文本、Recorder 写入权限 |
| `tests/test_application.py` | 5 项通过：讨论与报告权限、消息一次性回复、失败普通退出与尝试上限、报告模块拔除独立工作、权限变化后的通道注册 |
| `tests/test_agent_lifecycle.py` | 17 项通过：固定 Agent 节点、自有记忆、取消/保存/分解确认、定向可达、跨重启离线恢复、30 分钟驻留策略、配置匹配复用、定制角色排除、五人小组复用、独立文件夹和清单、FIFO/故障结果、持久队列、组件拔插及离线旧链接清理 |
| `tests/modular_shared_runtime_test.cjs` | 源码后端和最终二进制均通过：原生模型循环、请求尾部、快照重建、文档压缩后重载、委托期间双向事件、组件撤权 |
| `tests/modular_creation_test.cjs` | 本次源码与最终二进制通过：七个独立上下文/Session、自有记忆工具、卸载及真实 SessionPersistence 恢复、第二个根的存储/会话隔离；小组成员无主动发送工具 |
| `tests/modular_shared_loader_test.cjs` | 插件补丁仅装配一个有效尾部驱动和对应 invariant |
| `tests/modular_adapter_test.cjs` | 替换原生循环后保留配置式 Agent 和并行工具上限 |
| `tests/test_components.py ComponentsTests.test_binary_rpc` | 最终二进制的项目根、多查询文本讨论装配及检查点通过 |
| Word 提示词导入 | 原导入保持文档正文；本次个人笔记引用调整为 Agent 自有记忆工具 |

旧 JS 业务内部对象测试已由 Python 应用测试和真实原生循环通信测试替代。没有进行真实模型的完整端到端任务或客户端窗口验收。官方工具挂载在原生创建测试中使用替身，真实权限弹窗未重新验收。

本次 Python discover 共 31 项：30 项通过，二进制用例随后单独通过。原生共享上下文测试使用本次二进制完成异步 call 接受、等待原生循环完成、报告返回、请求尾部及组件撤权验证。空闲计时用可控时间状态测试，未实际等待半小时。

## 运行

Python 测试需安装相应节点依赖（例如 pandas）。分别执行上表 Python 脚本；二进制用例设置 `DATANET_TEST_BINARY=1`。构建使用 `python scripts/build_backend.py`，然后将 `build/dist/datanet-backend` 同步到 `adapters/harness/runtime/backend`。

原生测试设置 `ELECTRON_RUN_AS_NODE=1`，以本机 Harness 可执行文件运行 `--experimental-vm-modules tests/<文件>.cjs`。PowerShell 将输出接到 `Out-String` 以等待 GUI 子系统程序完成。默认使用成品二进制；如设置 `DATANET_TEST_PYTHON` 则使用指定解释器和源码入口。原生 SDK 可由 `DATANET_NATIVE_MODULES` 指定；测试数据保存在 `build/test-data`。

## 0.3.5：人数与去中心化协作

- `tests/test_cooperation.py`：9项通过，覆盖1/7名普通成员、完整轮次归档、Python直接装配、同组通信权限、认领冲突、真实临时 Git 合并及冲突保留、全体同一候选验收、否决旧候选、预算收尾、重启不重做、旧成员加入新组和模块拔除。
- 相关委托回归：FIFO、失败结果回送、持久队列恢复3项通过；文本连接兼容验证3项通过。
- `tests/modular_cooperation_test.cjs`：源码及最终 Windows 后端均通过。使用实际 Harness AgentRegistry/AgentLoop 和模拟模型，验证动态人数、独立成员会话、动态协作工具、临时尾部状态、共同验收、组级结果唤醒根节点、工具撤权及关闭流程。
- 原生 Git 子进程使用独立空输入，避免继承后端 RPC 管道；后台子进程隐藏窗口。

没有使用付费 API，也没有进行真实模型的完整业务测试。官方文件、终端工具装配代码沿用现有实现，原生最小验证中的能力挂载使用替身。

## 连续任务修复（源码，待文档编辑后再打包）

- `tests/test_group_runs.py`：5项通过。覆盖讨论组新任务及相同任务显式重跑、省略任务读取已有成果、中断后续跑、重启后接新任务；协作组旧循环收尾后再次启动、所有终止状态再启动、旧失败回调及旧超时隔离；两组历史文件同时恢复，历史成果保持独立，成员会话、记忆和已整合代码保留。
- 相关 `test_cooperation` 回归9项通过。
- `tests/modular_cooperation_test.cjs`：最终源码通过实际 Harness AgentRegistry/AgentLoop 验证，两种小组分别连续运行两个任务，保留会话、独立运行ID及归档，每次协作向根返回一次结果。模型和官方能力挂载使用替身，未调用付费 API。
- 本次没有重建 Windows 后端或打包。现有 0.3.5 插件包尚不包含连续任务修复；等待提示词、说明文档编辑完成后统一构建。

## 文件路径认领（源码）

- `tests/test_claim_paths.py`：5项最小测试通过。经已注册的组件工具验证可选 `paths`、路径规范化与去重、Windows 大小写与尾部点别名、文件及目录重叠、不同目录同名文件、并发认领只有一名成功、`extend` 冲突时整体保持原认领、所有权及完成/释放后的路径可用性。
- 验证认领路径进入共享记录和请求尾部，工具声明包含 `paths` 与 `extend`，旧版无路径认领兼容，保存后重新打开后端可恢复路径。
- 未调用付费 API，未运行完整端到端任务，未重建后端或打包。
