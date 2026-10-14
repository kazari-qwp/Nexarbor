# 工单、可选回复与尾部精简最小验证

## 实现范围

通信由 toolboxes/agent_messaging 管理；协作状态由 network_presets/decentralized_group 管理；Windows Python 环境由 adapters/harness/framework/windows-terminal.js 管理。Python 基础框架未添加上述业务分支。

send 和 team_send 新增 message_type=work_order|reply，缺省为 work_order；一次性回复自动归为 reply，正文前置“此为回复，可以不回。”。已读状态与可回复状态独立持久化。原生 agent/request-tail 在消息进入上下文后转发 context/admitted，仅传消息 ID；回复已读后停止提醒。工单阅读后仍待处理，回复或 pending_messages action=close 后结束。已有消息按 reply_to 迁移类型。

执行尾部仅含小组与阶段；当前候选未获该成员批准时才提示待审核。状态工具 section=summary|claims|records|candidate|all 按需返回。完整共享记录和验收路径继续保存。

默认 python 使用工作区专属、保留系统包的虚拟环境，兼容代码通过 .pth 加载，不依赖模型保留 PYTHONPATH。TEMP/TMP 指向工作区 .datanet/tmp。tools/execute 只为对应 Agent 的 pwsh 执行补充环境，随后还原原始参数；仍由官方工具进行审批和沙箱执行。tools/post-execute 附加具体错误建议。

显式指定工作区环境以外的解释器，或用 -S 禁用 Python site 初始化，不由这条默认启动路径接管；原有兼容入口仍保留。未修改全局 Python 安装或关闭沙箱。

## 验证

- Python 最小用例：通信生命周期 5 项、上下文位置 4 项、认领与路径冲突 5 项；既有一次性回复权限和指南路由 2 项，共 16 项通过。
- 真实 Harness 原生循环 + 编译后端：两次小组任务、会话复用、工具查询、候选验收、组件停用权限、历史追加机制，以及可选回复进入模型后已读提醒消失，通过；模型为 mock，无付费请求。
- 真实 Windows restricted-token PowerShell：覆盖 PYTHONPATH 后，自定义模块、私有临时目录读写删除、子 Python 进程通过；工作区外写入仍被拒绝；无 Python 时普通终端入口仍可用。证据 build/test-data/terminal-env-x5sFvw/result.json。

未重新运行完整付费 hone 项目，因此不声称模型调用次数已经降到某个数值。

Agent 可见改动与原文：[审阅文件](../AGENT_MESSAGE_TAIL_REVIEW.md)。
