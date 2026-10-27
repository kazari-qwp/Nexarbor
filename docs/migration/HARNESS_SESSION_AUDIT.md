# DSH 会话、容量与超时迁移核对

2026-10-28：用户要求完整复用 DSH 会话，输出、上下文与各层超时参照原项目；允许修正压缩接线，并明确不重跑中断小镇，从断点继续。

实际问题：adapt/harness/native/host.cjs 已使用原生 AgentLoop.create/resume、SessionStore、SessionProjectionRegistry 和 JSONL 持久化，但未挂载 tokenMeter/compaction。原项目 adapters/harness/studio/runtime/host.cjs 与 makers/model-host.cjs 的独立宿主也漏挂；旧 framework/adapter.js 挂在完整 DSH 主容器内，不能据此认为另起的独立宿主自动继承插件。新旧 AgentLoop 的 lib/index.js 与 invariant.js 经归一换行后逐字相同。压缩不是 HTTP 通信层自动提供的能力。

现由 adapt/harness/runtime/session-services.cjs 挂载安装包的 dsh-token-meter、dsh-compaction-tool-result-pruner、dsh-compaction-image-offload、dsh-compaction-basic；在日志恢复前注册。实际算法、触发、摘要、重试、投影和 surface replacement 均由 DSH 实现，不自制截断或对话缓存。兼容探测同步检查这些依赖。API 模型目录可向原生适配器传递 reasoningEfforts/compat；Agent 选项不混入目录元数据。

| 项目 | 原项目依据 | 当前处理 |
| --- | --- | --- |
| 默认上下文 | configs/agent-defaults.json：600000 | 读取同一配置，删除验收脚本的 128000 |
| 默认输出 | 同文件：50000 | 默认不变，删除验收脚本的 10000 |
| 小镇、根协作验收 | run_learning_town_eight_days.mjs / run_learning_root_hone.mjs：low、16000 | 保留该明确覆盖，contextWindow 仍取默认 |
| 资料库验收 | run_learning_knowledge_consumer.mjs：low、20000 | 后续原驱动沿用，不能套小镇的 16000 |
| 流式空闲 | 原 model-adapters.cjs：60000 ms | 沿用原值，无普通请求重试 |
| Agent 执行 | 原 runtime/host.cjs：至少 86400 秒 | 沿用原值 |
| 官方工具 | 原 official-tools.cjs / official-runner.mjs：86400 秒，RPC 另留 60 秒 | 沿用原值 |
| Python 长操作 / 脉冲 | 原工作流 86400 秒，RPC 86460 秒 | 沿用原值 |
| 普通 Bridge RPC | 原 framework/bridge.js：30000 ms | 沿用原值，不整体放宽短操作 |
| Studio RPC | 原 studio/rpc-timeouts.mjs：普通 45000 ms，长操作 86460000 ms | 前端迁移时保留原分层，当前不声称 Studio 已迁完 |
| 新验收代理总时限 | 新脚本额外添加 180000 ms | 删除；取消跟随原生请求，空闲保护由 DSH 承担 |
| 新验收外层时限 | 新 Python 脚本额外添加 2400 秒 / 每天 | 删除，避免覆盖原生任务期限 |

压缩参数直接采用安装的 DSH 默认值：自动开启、thresholdRatio 0.8、retainRatio 0.16、headroomTokens 65536、摘要输出预算 65536、compactionRetries/maxOverflowRetries 各 1。摘要输出预算是 DSH 原生辅助请求预算，与应用普通输出上限分开。没有为了让测试通过修改这些值。DeepSeek 的 low/high/max 和 none 官方说明：https://api-docs.deepseek.com/guides/thinking_mode/；实际请求体已验证 reasoning_effort=low。

验证：420 项 Python 回归通过（190.718 秒）；真实安装 DSH 0.2.1-rc.2、0.2.0-rc.2 均完成主动压缩、一次超限→压缩→重试成功、压缩取消关闭括号且可继续、原始日志保留、600000 上下文记录、普通请求 50000 输出/low、同会话冷重开；另原生日志/锁位置三项和生产 Python RPC 工具桥通过。模型仅为本地 HTTP 夹具，付费调用 0。入口 scripts/verify_native_compaction.py，完整证据 evidence/2026-10-28-native-compaction.json。

## 中断小镇的恢复依据

原运行 build/native-town-newcore-9h_00tqg 停在第 17 时刻，前 16 完成。稳定节点提交为 1383（摘要 892ff2083ab8c409af25dc71a47f21595a09fb96fc1d7c917abbb62ac56d78be），脉冲 sequence=16、phase=completed、active_signal=None。不能使用已预留第 17 次脉冲的提交 1384。原自动检查点协调器在连续脉冲间未及时发布该完整点，故按用户断点授权从校验通过的原状态日志提取提交 1383，并以第 16 波 finished_at=1793114454.493974 截取原生会话。

7 个前缀均用 NativePositions.read 校验；最后事件都是 completed turn/end，工具未配对数为 0。前缀长度分别为 902、892、989、924、887、589、1026。原文档中较早的节点级 context_cursor 有处于工具过程的游标，不能直接当作完整波次断点。scripts/town_resume/contexts.cjs 计算并验证准确日志前缀；prepare.py 验证原 SQLite 链并调用既有 restore_bundle；bind.mjs 用原 agent-context-restore 创建 DSH 原生前缀分支，再用既有 acknowledge/bind/checkpoint 接口登记。原会话及失败第 17 时刻日志全部保留；新分支有明确原生 parentSession，不覆盖日志或重放前 16 时刻。

已离线恢复至 build/town-resume-y7_z7dk1/runtime，7 会话已确认，恢复检查点 05188b9404ea4b5d813d185ff6ad9cac，恢复过程模型调用 0。付费续跑入口：scripts/verify_native_town.py --days 5 --resume-directory build/town-resume-y7_z7dk1/runtime。目标只执行第 17–25 时刻；每个完成时刻显式发布原生会话与节点一致的完整检查点。保留原 0 时刻 initial-state.json，续跑初态另存 continuation-initial-state.json。前 16 结果保留，第 17 次失败消耗单列，最终分别记录有效运行消耗和包含失败尝试的总消耗。

恢复资源补充：首次恢复目录缺少 DSH attachments/v1 的一个 45788 字节对象，原生执行器在请求前拒绝，API 请求 0；该失败目录原样保留。prepare.py 现在一并复制附件库，并逐文件 SHA-256 核对。重新恢复后的当前目录以本页更新路径为准。

API 路由补充：恢复后 7 次请求被上游以 HTTP 422 拒绝（DeepSeek 不接受 developer 角色），无 usage、无模型工具执行。low 声明使通用 OpenAI 路由原有自动检测不再适用，现显式 supportsDeveloperRole=false，让官方适配器转换为 system。离线夹具新增角色断言，两版 SDK 再次通过。该失败尝试单独保留，不并入成功波次统计。
