# 公共经验库

## 位置与范围

实现：`experience.js`；初始已验证经验：`experiences/seed.json`。
默认运行数据：`<storage>/experiences/library.json`，独立于会话和网络快照保存。
用插件配置 `experienceDirectory` 指向同一目录可跨项目复用。默认只跨同一项目的会话，不自动共享给全机所有项目。经验内容应是可共享的操作经验，勿提交密钥或私有任务材料。

归属标签：`common:*`（通用）、`tool:pwsh`（工具）、`toolbox:engineering`（工具箱）、`role:operator`（职责）、`node:<实际ID>`（实例）。一条经验可含多个标签，无需复制。
共享目录下 node ID 必须由配置者保证唯一；跨项目通用内容优先标记职责/工具。

## 装配和读取

所有 Agent 平时只展示 `handle_problem` 问题入口；进入后按需展示 `experience_query`、`experience_submit`、`incident_query`、`incident_resolve` 等临时工具。详细顺序与权限见 [问题处理入口](PROBLEM_HANDLING.md)。
`experience_maintenance` 提供 `experience_review`，仅显式装配者能使用；不自动给根 Agent。
授予子 Agent 时仍须加入宿主 `allowedAgentToolboxes`。根 Agent 可在 `rootToolboxes` 显式加入维护包。

启动加载少量 `core:true` 的通用、职责、节点经验。Agent 预设 JSON 支持：

```json
{"experience_role":"operator", "experience_refs":["operator-evidence"]}
```

工具箱 JSON 可设置 `experience_refs`。进入排障通道后，调用相关工具时按 tool/toolbox 标签及引用加载（包括官方工具），动态系统提示词在后续模型请求可见；这不是执行前的第二次授权或模型审批。同一会话按经验 ID 去重，自动上下文最多 12 条。首次调用由当前模型请求发出，因此这些经验不保证能防止首次调用的错误。
根配置支持 `rootExperienceRole`（默认 project_root）及 `rootExperienceRefs`。
职责与引用随 Agent 绑定持久保存，重建/恢复时继续使用。

按需查询：

```json
{"kind":"tool","id":"pwsh","query":"引号","limit":6}
```

query 为简单关键词包含匹配；支持 `entry_id` 精确取条目，`offset` 分页。不是语义检索或 RAG。
查询默认 `status:all`，包含 verified 和 pending；可用 verified/pending 筛选。每条结果保留状态，pending 仅作线索，不进入自动提示词，即使精确引用或手动查询也不会被标成正式建议。
查询结果包含依据和适用版本；版本由维护者审核，程序不自动判断兼容性。经验不授予权限、不代替工具描述或 Skill 指令。

## 候选提交与审核

已解决并验证的问题调用 experience_submit：

```json
{
  "applies":[{"kind":"tool","id":"pwsh"}],
  "trigger":"内联 Python 引号解析失败",
  "advice":"复杂代码保存成脚本文件后运行，并检查退出码。",
  "evidence":"运行脚本得到 PASS，退出码 0；附可核查记录路径。",
  "version":"PowerShell / Python"
}
```

框架附提交者、ID、时间，状态 pending；候选可被普通查询读到，但不进入自动启动/工具经验上下文。未解决问题按当前委托判断：仍可继续或交付失败结果时用 problem_defer 记录原因、影响及继续依据；确实阻塞自身委托时，查经验和获准排障后使用 datanet_feedback 并填写 task_blocker，由框架自动采集。
维护者用 experience_review：list（默认 pending）、publish、reject、merge、retire、set_core。
list 每页 10 条，用 offset 翻页。publish 可通过 changes 修正字段及 core；必须由维护者核实证据，代码不代替事实审查。merge 需要已验证条目的 merge_into，标记候选被合并；如需改正式建议应发布修正版并 retire 旧条目。审核操作保留审计记录。

```json
{"action":"publish","id":"候选ID","changes":{"core":false}}
```

正式经验被停用后不再供默认查询或新会话加载；当前会话已读内容不主动撤回。重复提交可由维护者合并，不做自动语义去重。

## 持久化与验证

同一进程内写操作排队；目录写锁防止跨进程并发覆盖，临时文件原子替换避免半个 JSON。锁被占用时明确失败，调用者稍后重试；崩溃留下锁时须确认没有写入进程再移除 `.write-lock`。不自动冒险释放别的进程的锁。

最小验证已通过：候选可查询但不自动加载 → 维护者发布 → 新操作员加载职责经验 → 运行时重启后仍可查询。
另验证重复加载去重、合并/停用、写锁保持原数据。Harness 生命周期采用 mock，Python 后端真实运行；本次未进行付费模型调用或打包安装。

后续：依据真实重复问题扩充条目；稳定规则提升到工具描述、Skill 或代码。暂不引入 RAG、自动发布、全量提示词注入。

## 自动阻塞与异常记录

`incidents.js` 负责采集。事件与执行记录也存于 library.json 的 incidents/runs，与经验 entries 分开。

- 调用 datanet_feedback 后自动记录 blocked/unresolved：自身ID、创建者、职责、工具箱、时间、版本、会话和执行ID、错误类别、简短说明，及最近失败工具的信息（有则保存）。发给上级仍只有自身ID和简短错误，并停止当前轮。
- 普通工具失败只更新最近失败信息；不每次产生阻塞事件。官方和框架工具通过 Harness tools/result 观察，框架异常还有直接捕获路径。
- 委托/讨论执行异常、超时、取消及模型截断单独标记 execution_exception，不当成主动反馈。进程被杀时不能当场写入，下一次启动根据未完成执行记录标记 interrupted；不自动重放任务。
- 初始化时补录后端已持久保存的反馈（按 feedback_id 去重）。补录旧数据可能没有最近工具错误；恢复来的事件不会冒充完整现场记录。
- 根 Agent 同样记录，无创建者时 creator_node_id=null。

不保存完整提示词、工具参数或任务全文，只保留会话/执行引用和截短错误；对环境中已知密钥及 Bearer 值脱敏。

```json
{"node_id":"root/operator","status":"unresolved","limit":6}
```

incident_query 返回 incidents 和近期 retry_runs；支持关键词、节点ID、状态、分页。它是只读共享诊断，不提供越过网络的节点操作权限。

更新提示词、补充工具箱不会自动解决事件。创建者用正常 call_agent 或 resolve_feedback/instruct 让下级重试，正常完成返回 retry_run_id。

```json
{"id":"阻塞事件ID","retry_run_id":"后续正常执行ID","evidence":"重试脚本输出 PASS，退出码 0","experience_id":"可选候选经验ID"}
```

incident_resolve 仅允许报告者、实际创建者或装配经验维护包者操作。框架检查重试为同一来源项目、同一节点、发生在事件之后且正常结束，并要求结果依据。正常结束不等于任务正确，依据仍需调用者核实；不是框架自动判定任务成功。失败执行ID或杜撰ID不能用来解决事件。
关联经验只建立引用，不自动发布候选。解决后的事件、未解决事件均可在问题通道内查询，状态明确。

新增验证通过：阻塞采集与最近错误、简短反馈不变、根节点采集、异常捕获、重试依据限制、创建者权限、进程中断补录和持久读取。仅本地验证，未付费调用/打包安装。
