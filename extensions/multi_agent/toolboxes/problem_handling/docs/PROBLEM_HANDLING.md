# 问题处理入口

## 平时与进入后

所有 Agent 默认具备 `handle_problem`，而经验查询、候选提交、阻塞查询、成功标记及自己的报错工具不常驻显示。少量 core 经验按职责/工具授权在启动时加载。创建者处理下级报错的 datanet_resolve_feedback 是管理工具，继续保持原有可用性。

调用：

```json
{"problem":"运行脚本遇到引号错误","origin":"self"}
```

入口不发送报错、不结束任务。它保存问题记录，加载 guides/problem_handling/AGENTS.md，并使用官方 Harness 的 scoped tools.register 临时装配：experience_query、incident_query、problem_attempt、experience_submit、problem_resolved、problem_defer、incident_resolve、datanet_feedback。

## 框架保证的流程

1. experience_query 查询非常驻经验；默认同时返回 verified/pending，保留状态。默认排除本 Agent 已常加载的条目；精确 entry_id 或 include_resident=true 可主动查它们。incident_query 可补充同类阻塞线索，但不能替代先查经验。
2. problem_attempt 指定刚查询到的 experience_id。尝试中可以使用原先获准的工具；进入不增加任何读写、终端或管理权限。查经验之前不能执行修复，单纯只读检查允许。
3. 验证成功后 problem_resolved 必填结果依据。必须有尝试开始后真实工具管线记录的成功操作；仅凭模型说“已解决”不能完成。
4. 没有适用经验或经验无效时，只有 self_repair 授权允许不填experience_id开始自主排障。自主修复成功必须先 experience_submit 提交候选，再 problem_resolved。未获授权不能靠进入入口获得自主权。
5. 未解决时先判断自身委托能否继续：可继续或允许交付失败结果，使用 problem_defer，填写 reason、impact、continuation；确实阻塞自身委托才 datanet_feedback，并填写 task_blocker。后者仍要求先查经验；获自主排障授权者须进入自主尝试分支。不得为退出伪造验证。
6. 报错依旧保持两类固定短文本（工具缺失/权限不足）及80字以内其他说明；保存阻塞库、通知创建者并结束当前轮。根节点无创建者，结果留在用户会话。

框架只验证调用顺序、授权与操作记录，不能机械证明一次成功读取/执行就解决了实际问题，具体判断与依据由 Agent 和审核者负责。

解决、未解决退出或报错后，通过 Harness 返回的 disposer 真正撤销临时工具；后续工具列表中消失，缓存的旧调用也不可使用。流程指南按需进入普通历史，正文被压缩后再次进入才重新加载；非常驻经验从未来系统提示词移除。problem_defer 保存 status=deferred，不记成功经验，原因、影响与继续依据持续渲染到系统上下文并在重启后恢复。origin 记录 self/subordinate/dependency；归属不等于阻塞判定。重新处理传原 problem_id，仅允许本节点重开其 deferred/interrupted/reported 记录，保留全部 attempts 与 dispositions；同来源同描述的未解决记录也会自动复用。默认每个问题最多3次尝试，可通过入口 max_attempts 降低；同目标的报错恢复另有持久预算，管理路径共用，详见次数规则。

未关闭问题时，正常任务完成不会被当成成功。框架异常、超时、中断仍自动记入异常库；未完成问题标记 interrupted。重启不盲目执行旧修复，后续进入入口重新检查问题。

## 自主排障授权

默认 false。授权是工具箱配置，例：

```json
{"source":"datanet","name":"handle_problem","options":{"allow_self_repair":true}}
```

预置 `self_repair` 小工具箱声明这一授权，无业务工具。宿主可把它加入 rootToolboxes；允许父 Agent 分配时，还须加入 allowedAgentToolboxes，创建子 Agent 时选择它。禁止仅修改提示词声称获得授权。

权限与工具列表不会因本次排障扩大；所有原有网络/管理/私有工具限制继续执行。父 Agent 的排障状态只约束自身，不干扰下级自己的工具调用。

## 经验复用与常加载

成功使用经验后写入 experience_uses，按 problem_id + experience_id 去重，统计 success_count、failure_count。真实工具最终结果用于验证；失败的最终结果不能当成功依据。

已验证经验成功5次时，设置 promotion_candidate，仍不会自动变成 core。维护者审查适用对象、失败情况与成本后，使用：

```json
{"action":"set_core","id":"经验ID","core":true}
```

只有装配 experience_maintenance 者能调用 experience_review 执行这一操作。core=false 可取消常加载；新会话按职责和工具匹配加载。待审核条目即使成功多次也不自动发布。

## 验证与范围

本次三个出口、问题归属、恢复次数限制及状态接口变更尚未运行测试，也未打包安装到客户端。当前已安装版本及既有会话仍使用原逻辑。

框架验证字段、状态、作用域和操作记录，不能机械判断 continuation/task_blocker 的业务理由是否成立，也不能仅凭成功工具调用证明问题实际解决。需后续通过成功、失败可交付和自身阻塞三条路径验证。

## 次数规则的按需注入

次数规则唯一的 Agent 文档源是 `guides/problem_handling/RECOVERY_LIMITS.md`。框架检查当前 Agent 的 handle_problem 工具授权：只有 allow_self_repair=true 且首次进入问题通道，才在该 Agent 的普通历史中注入专用说明；正文仍在上下文时不重复注入，被压缩后再次进入时重新注入。模型声明的权限不参与判断。次数约束仍在代码执行，对未注入文档的 Agent 也有效。

## 恢复状态接口

根 Agent bind_agent 现在记录真实 session_id。datanet_recovery_status 对旧记录中的 session_id/kind 使用 null，对其他已知可选字段使用 null/空列表；同时返回 recovery_budgets。JSON返回值不通过序列化悄悄丢弃缺失字段。恢复预算保存在经验库 recovery_budgets，按插件 storage 来源和目标节点隔离，不修改原 Python 项目。
