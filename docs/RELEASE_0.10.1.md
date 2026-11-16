# Nexarbor 0.10.1

修复更新 DeepSeek Harness 后，双击 NPC 打开对话时报 `TOOL_RUNTIME_SCHEDULER` 导出缺失的问题。本版本已在 DSH **0.2.2-rc.3** 上验证。

- Agent 工具调用接入 DSH 的原生工具执行器，保留原来的 Agent 循环、上下文组装、权限与会话恢复逻辑。
- 官方文件、终端工具同步适配新的执行入口与结果 Schema，原工具接口和返回内容保持一致。
- 启动前实际加载适配层，检查 SDK 导出接口。版本不兼容时直接给出对应提示。
- 核心的 16 个 Python 文件与上一运行包逐字节一致，应用模块和业务规则没有修改。

## 安装

下载 `Nexarbor-0.10.1-win-x64.zip`，完整解压到新目录，运行 `Nexarbor.exe`。在“设置 → DeepSeek Harness 路径…”中选择本机 DSH **0.2.2-rc.3** 的可执行文件。

仍需单独安装 Git 与 DSH。包内包含 Electron、Python、基础依赖及原来的六份演示。Agent 历史消息从当前机器的 DSH 日志读取。

## 验证

用仓库源码启动真实 Electron，在“小镇最终”副本上打开全部 7 个 NPC 对话。阿森通过真实 DeepSeek API 调用记忆工具并回复，耗时 7.355 秒。随后点击“单步”，小镇由第 30 时刻推进到第 31 时刻，7 人活动全部完成，耗时 118.686 秒。冷重开后会话 ID、消息和运行时刻一致。

这次真实验收共 80 次有 usage 的响应，未缓存输入 856,148 token，缓存输入 7,933,824 token，输出 27,907 token，合计 8,817,879 token。验收在副本进行，随包小镇最终示例仍为第 30 时刻。

526 项 Python 回归、137 项前端回归、6 项桌面回归通过。原生会话与锁恢复、压缩与溢出恢复、冷重开前缀一致性、RPC 记忆工具、官方终端工具和两种制作 Agent 的本地模型回归均通过。

[真实验收记录](migration/evidence/2026-11-16-dsh022-town.json) · [NPC 回复截图](migration/screenshots/dsh022-npc-reply.png)

附件 `SHA256SUMS.txt` 用于校验 ZIP，`VERIFICATION.json` 记录回归与运行包检查结果。
