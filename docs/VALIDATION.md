# 本次验证

本次验证覆盖 Python 业务迁移、双向通信和最终 Windows 后端。原生 Harness SDK 使用本机 0.2.0-rc.2，模型由本地模拟响应提供，无付费 API 调用。

| 入口 | 本次结果与覆盖 |
|---|---|
| `tests/test_components.py` | 5 项源码测试通过：Python 本体独立、组件关闭/恢复、数据保留、本地工具箱撤权；二进制用例另行运行 |
| `tests/test_shared_texts.py` | 3 项通过：常驻/查询文本、多个项目来源、根查询文本、Recorder 写入权限 |
| `tests/test_application.py` | 4 项通过：Python 讨论与报告权限、消息一次性回复、失败普通退出与累计尝试上限、报告模块拔除后讨论及执行记录独立工作 |
| `tests/modular_shared_runtime_test.cjs` | 源码后端和最终二进制均通过：原生模型循环、请求尾部、快照重建、文档压缩后重载、委托期间双向事件、组件撤权 |
| `tests/modular_creation_test.cjs` | 最终二进制通过：普通节点和五名小组成员使用七个独立上下文/Session，小组成员无主动发送工具 |
| `tests/modular_shared_loader_test.cjs` | 插件补丁仅装配一个有效尾部驱动和对应 invariant |
| `tests/modular_adapter_test.cjs` | 替换原生循环后保留配置式 Agent 和并行工具上限 |
| `tests/test_components.py ComponentsTests.test_binary_rpc` | 最终二进制的项目根、多查询文本讨论装配及检查点通过 |
| Word 提示词导入 | 三份文档的非空白字符与目标提示词完全一致 |

旧 JS 业务内部对象测试已由 Python 应用测试和真实原生循环通信测试替代。没有进行真实模型的完整端到端任务或客户端窗口验收。官方工具挂载在原生创建测试中使用替身，真实权限弹窗未重新验收。

## 运行

Python 测试需安装相应节点依赖（例如 pandas）。分别执行上表 Python 脚本；二进制用例设置 `DATANET_TEST_BINARY=1`。构建使用 `python scripts/build_backend.py`，然后将 `build/dist/datanet-backend` 同步到 `adapters/harness/runtime/backend`。

原生测试设置 `ELECTRON_RUN_AS_NODE=1`，以本机 Harness 可执行文件运行 `--experimental-vm-modules tests/<文件>.cjs`。PowerShell 将输出接到 `Out-String` 以等待 GUI 子系统程序完成。默认使用成品二进制；如设置 `DATANET_TEST_PYTHON` 则使用指定解释器和源码入口。原生 SDK 可由 `DATANET_NATIVE_MODULES` 指定；测试数据保存在 `build/test-data`。
