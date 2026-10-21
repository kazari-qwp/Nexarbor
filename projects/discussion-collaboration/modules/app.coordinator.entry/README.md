# 任务编排器

把一次任务依次交给讨论组和执行组，再组织候选验收。根节点只连接小组入口，成员通过执行组自己的入口提交和表决。

| 操作 | 作用 |
| --- | --- |
| `start` | 启动讨论，保存本轮目标与讨论会话编号。 |
| `handoff` | 讨论完成后，将 Recorder 的成果整理为任务并打开协作板。 |
| `integrate` | 收集成员提交，生成 Git 候选，并沿验收频道通知成员。 |
| `promote` | 检查候选已通过全员验收，完成发布与本轮编排。 |
| `status` | 汇总讨论、任务板、整合器及最近错误。 |
| `stop` | 停止当前阶段，保留已产生的成果和状态。 |

这六项操作通过 `app` 频道提供给根 Agent。成员的 `submit`、`approve`、`veto`、`read` 由 [collab.participant](../collab.participant/README.md) 提供。

## 配置与连接

`discussion_node` 指向讨论入口；`board_node`、`integrator_node` 指向装有任务板和 Git 整合器的执行入口。同一执行节点可以装配后两个模块。

对应模块 ID 由 `discussion_module`、`board_module`、`integrator_module` 配置；默认值使用本项目附带的实际修订版。调用讨论走 `discussion`，调用任务板和整合器走 `collaboration`。`review_channel` 默认 `collaboration.review`，只用于通知成员验收；`accept_channel` 默认 `collaboration`，用于候选重开等整合器调用。节点与边需允许相应频道。

`activity_timeout_seconds` 控制本模块发出信号的总时限及目标处理时限，默认 86400 秒；可按任务调整。

## 状态与恢复

同一实例保留一个当前运行。相同幂等键返回原运行，避免重复开启。讨论尚未完成或缺少 Recorder 成果时，`handoff` 明确报错。候选被否决后可以再次整合；修改由成员在各自分支完成，成员重新提交后形成新候选。验收通知失败会记录错误，已生成的候选保留。

本模块保存编排状态，通过下游公开接口协作。任务认领归任务板，真实 Git 操作和全员认可判断归整合器。
