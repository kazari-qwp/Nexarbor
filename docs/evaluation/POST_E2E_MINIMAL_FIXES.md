# 完整测试后修复与最小验证

日期：2026-10-14。改动仅在模块化成品目录；没有调用付费模型，没有重新运行 hone 完整课题。

| 发现的问题 | 本次处理 |
|---|---|
| 讨论同轮串行调度 | 同轮全部成员并发，全部提交后进入下一轮；成员使用共同的轮初笔记快照 |
| 每个成员重复完整验收 | 提案附测试脚本、结果和真实终端记录；其他成员阅读材料，有疑问再补测 |
| 已批准者仍被要求继续推进 | 提案者和批准者结束当前循环等待，否决或新消息仍可唤醒 |
| 为不同日志重复运行测试 | 独立日志工具保存原始工具结果和官方完整输出文件，支持分页读取 |
| 报告变动引起复制、哈希核查 | artifacts_path 位于源码 Git 工作树之外；每个候选保存对应提交及验收材料快照 |
| 私有临时目录无权限 | Harness 独立适配层保留父目录中匹配当前受限令牌的能力 ACE |

根节点反复查询状态、报告 ID 与等待 ID 的使用方式按用户要求保留。

## 最小测试

- `tests/test_revision_minimal.py`：两轮并发与共同快照、轮次屏障、快照持久恢复、成员异常时取消同轮成员、完整 spill 日志保存与分页、日志归属、材料快照、批准后等待与否决唤醒。
- `test_cooperation.CooperationTests.test_peers_claim_merge_and_quorum_completion`：真实 Git 整合与全员通过规则。
- `test_cooperation.CooperationTests.test_reject_stale_vote_budget_stop_and_restore`：空初始提交的候选、旧投票拒绝、停止及恢复。
- `test_group_runs.GroupRunTests.test_discussion_interrupted_task_resumes_then_restarts_after_restore`：并发中断后不重复已提交成员，持久恢复后承接新任务。
- `tests/windows_private_temp_test.cjs`：实际 Harness Windows ACL SDK；Python3.11/3.14私有目录写入和清理、私有 temp SID、工作区外/其他工作区/只读写入拒绝、普通目录及非受限 Python、兼容桥生命周期。修复前复现写入失败。
- `tests/modular_cooperation_test.cjs`：真实 Harness 循环与重建后的成品后端、模拟模型；两次讨论及协作、原生 tool/result 到 Python 的完整日志保存和候选附件、结果通知与循环结束。

终端日志优先复制官方结果的 spillPath；官方输出缺失时记录完整性状态，不伪造缺失内容。后台任务的查询结果也保存；尚未取得的后续输出须等待原任务并读取日志。

业务处理分别放在 discussion_group、decentralized_group、tools/command_logs 和 toolboxes/command_logs。Windows 兼容与环境桥在 adapters/harness，不进入 Python 基础框架。
