# 工具原生移除复查（2026-10-17）

用户要求重新确认 Harness 是否支持工具 in-history 更新，以及压缩后为什么不清理停用工具。本次只做隔离调查，没有修改运行配置、工具权限策略或用户客户端。

## 结论

当前安装 Harness SDK 0.2.0-rc.2 的模型能力配置支持 `toolUpdate: in-history`，也支持 `addition-only`。该参数位于模型目录（models）中，不是直接传给 DeepSeek HTTP API 的请求参数。`systemPromptUpdate` 为另一个独立参数。

本地 SDK 接受 in-history，能够将当前有效工具与历史声明投影为原生 tool_removal；官方 Messages 服务端仍拒绝该事件。因此当前账户通道不能仅靠修改参数启用完整原生工具移除。

## 最小实测

使用与 NPC 实测相同的已登录 DeepSeek Account 凭据，凭据仅在内存中使用。调用目标限制为 https://api.deepseek.com；模型 deepseek-flash，思考关闭，每次输出上限64，总计最多3请求、90秒，不执行任何工具。

| 阶段 | 结果 | 原始证据 |
|---|---|---|
| 两个工具的普通基线请求 | HTTP 200，READY | wire[0] |
| toolUpdate=in-history，移除一个工具 | HTTP 422，unknown variant tool_removal | wire[1] |
| 原生 surface replacement 后，只用有效工具建立新声明系列 | HTTP 200，COMPACT_ACK；请求只含 retained_probe | wire[2] |

移除请求带 SDK 自动添加的 mid-conversation-tool-changes beta 头，原始 JSON 中实际包含 tool_removal；不是参数没生效或只在客户端假装卸载。当前服务器错误列出的允许类型包含 tool_addition，但不包含 tool_removal。

第三阶段使用原生 Session surface replacement 与 request/header reason=series，模拟摘要提交后的工具投影边界；没有调用完整摘要模型或客户端压缩命令。它验证了新系列可以只带当前有效工具，不能据此声称已接入产品自动压缩回收流程。

成功的两次请求合计未命中输入597、输出6、总603 token；被422拒绝的请求没有返回usage。第一次探针的本地 replacement 范围误含系统节点，SDK拒绝；修正范围后复用前两阶段结果，仅补第三次请求，没有重复付费基线和移除测试。

## 当前产品为什么一直保留

- in-history.patch.yml 和 cordis.patch.yml 将 Flash 配为 addition-only。SDK在此模式过滤历史 removal 事件。
- ToolPermissions.register 的释放回调只设置 enabled=false，不移除注册定义；agent/tool-schemas 仍按 map 中是否出现过保留它。
- 官方工具授权更新也保留 retained / officialSeen，执行时用 guard 阻止越权。
- 这些状态属于适配器的运行态，不属于会话正文；压缩正文不会清理它们。新请求系列再次得到旧清单，因此停用定义依然存在。

隔离对照确认：新系列传入仅有效工具时，旧声明消失；模拟适配器继续传入两份定义时，两份仍保留。压缩后残留有明确的适配器原因，不应当作原生 Harness 无法重建工具清单。

## 两种模式的准确区别

在历史移除前后，in-history 保留本系列历史声明，通过 removal 标记工具失效，目的是保留旧前缀；它不等于立即从请求 JSON 的 tools 声明区抹掉全部旧定义。新系列/压缩后按有效清单重建，才有机会真正去掉废弃定义。

addition-only 会过滤 removal；若直接删当前工具定义，投影的 tools 声明区也可能变化，因此不能把频繁删除当作免费保持缓存的方案。

## 后续建议（尚未实施）

维持当前系列内新增与执行禁用；在成功压缩、建立新请求系列时，仅用仍授权工具重建清单，回收停用动态定义并重置 officialSeen/retained。执行 guard 仍保留。需补充部分压缩保留旧 tool-call/result 的情形、重新开放工具、同名 schema 更新、恢复/分支等测试；本次未改消息队列或卸载策略。

证据与隔离脚本保存在 build/tool-update-investigation-20261017/{result.json,probe.cjs,run.py}，该目录被Git忽略；原始证据不包含鉴权头或凭据。当前SDK源码副本也保留在同目录供核对。

## 后续实施（2026-10-17）

已在 Harness 适配层接入成功的 compaction/end：回收已停用且不被当前 surface 的 tool-call 引用的动态定义，清理官方工具的 officialSeen 和 retained 白名单；当前授权和执行 guard 保持不变。部分压缩保留的调用及结果继续拥有声明，直到后续压缩移除它们。失败压缩不清理，跨 Agent 状态隔离，重新注册支持新定义且旧 disposer 不会误停用新注册。

原生自动压缩发生在 agent/pre-step，而该位置的工具清单可能已经装配；溢出重试也会复用先前装配。AgentLoop 因此增加基于 surface.replaceGeneration 的重装配：只在 surface replacement 后重建系统提示和工具清单，普通请求维持原流程。核心网络、消息队列、Agent 提示词和工具描述未改。

最小验证使用已安装 Harness SDK 的真实工具注册表、addition-only 投影、BasicCompactionEngine 事务、TokenMeter、请求重建 invariant 和 JSONL 磁盘恢复。摘要与模型输出使用确定性测试适配器，不调用付费 API。新增 tests/native_tool_compaction_test.cjs 覆盖成功/失败压缩、部分压缩、作用域隔离、重新授权、同名定义更新、自动压缩后首个请求、溢出重试，以及压缩后未写新请求头就关闭再恢复的情况。

另通过原生权限、日志恢复、请求纠错和 NPC 脉冲最小集成测试。旧 multi_agent 的 modular_shared_runtime_test.cjs 未通过启动：其网络预设仍为旧序列化格式，Backend 构造时报告 network 字段应为 version/nodes/delegations/signals；这发生在 ping 和工具执行前，属于此前暂缓的应用兼容性问题。本次未扩大范围修改旧预设。
