# 实际讨论协作应用验收方案

当前原 profile 指向 projects/discussion-collaboration，共 15 节点、10 Agent、12 份受管理文档。新项目为 projects/discussion_collaboration，拓扑、初始正文、模块配置、频道和预算由一次性转换脚本保留；宿主工具用真正的 CallableTool，terminal_ref 转为其实际名称。运行时不导入旧工程。

## 已验证

- 新模块会话/协作板/Git/协调器、真实 SDK 命令与手动完整业务阶段均已通过专项。
- 实际 15 节点配置、31 个宿主工具、外部组装器 prepare、Agent 记忆隔离和冷重开通过。
- 生产 RPC 装载实际项目，discover 预览仅编码工具声明；实际终端、便笺写入/上下文/重开通过：build/native-discussion-project-z4y62vax/verification.json。
- 共用 app/projects/Project 提取后，6 项小镇项目/模板回归通过；原 DSH 本机模型桥 5 次 HTTP、同会话续跑再次通过：build/native-bridge-90iomeug。

## 原验收脚本差异

原 scripts/verify_native_apps.mjs 的 groups 分支仍使用 discuss_eng/discuss_pm/discuss_qa、collab_eng/collab_qa、board_discuss/board_notice 以及 expected_revision 任务接口。这些 ID 与协议不属于当前 profile 的实际 15 节点应用。不能把旧脚本当成新核心不兼容，也不能重新造一份旧简化网络。

以当前实际应用覆盖原断言的目的：真实成员讨论、真实协作、私人记忆、全量保存重开及同会话继续；同时验证当前真正存在的 Leader/Recorder 会话、认领协作、独立 Git 成果、候选全员投票及根编排器。

## 真实模型步骤

1. 使用新项目全量 15 节点，宿主经生产 RPC、NativeRunner、OfficialToolsRunner 执行。API 配置复用本项目 .env，使用与小镇相同的已验证 API profile，不打印密钥。
2. 在新的 build 验收运行目录中准备真实 workspace/repository Git 仓库，只放 README 小任务输入。四项独立标准库 Python 功能，各有独立模块和测试文件；由 Agent 自主认领、创建 worktree、实现和提交。验收脚本不代写成果、不开业务旁路。
3. 根 Agent 只启动一次一轮讨论后结束；宿主等待独立信号运行器处理完已有及新排队信号。校验 5 个席位的完整发言、Leader 决策、Recorder 成果与 completed 状态。
4. 根 Agent 将实际成果交接执行组。等待 4 位执行 Agent 完成活动，检查任务/认领/提交与真实 Git 分支及文件；不得替 Agent 补交业务结果。
5. 根 Agent 请求实际 Git 整合。4 位执行 Agent 沿 review 信号检查同一候选并投票；只有所有仍参与成员通过后才发布。失败按原业务状态保留，不放宽模块验证或修改核心绕过。
6. 根 Agent promote；运行候选中的标准库测试核实真实成果。记录候选提交、成员提交、审批和运行状态。
7. 全量保存并关闭/重开；确认已建立的原生 session ID 保持，私人 Markdown 记忆存在，再由根 Agent 读记忆/状态继续一轮，保存 transcript 与 JSONL 游标证据。

## 时间与 token

代理只转发真实 API，不产生模型替身回复。逐请求记录 HTTP 状态、耗时及服务器 usage（仅数字）；每阶段记录开始/结束、请求数和输入/输出 token。请求上限与总时限属于验收进程，不改业务模块。小镇已获用户接受的推理输出差异不再重复调查。

旧 groups 脚本与当前真实应用任务规模和拓扑不同，没有可直接宣称性能提升/退化的同任务旧基线；明确记录这一限制。仍监测异常重复调用、错误风暴、阶段耗时和 token 激增，明显异常按用户要求暂停并汇报。

## 仍待完成

真实模型验收脚本和运行尚未完成。之后还有资料库 catalog/tasks、完整 Studio/前端、资源/复制服务、全部旧文件语义审查、制作 Agent Skill/提示词更新。任何一项未完成不能宣称全量迁移完成。
