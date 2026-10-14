# 原生上下文更新与缓存验证

## 已接入的路线

DataNet 部署配置使用 `deepseek-official / deepseek-flash`，官方 Messages 地址 `https://api.deepseek.com/anthropic`，凭证引用 `DEEPSEEK_API_KEY`。上下文 500000，输出上限 50000，默认思考 high。

- 系统提示：官方 `systemPromptUpdate: in-history`，旧前缀保留，新系统正文加入历史。新请求系列（例如压缩后）由 Harness 合并当前系统提示。
- 新增工具：官方 `toolUpdate: addition-only`，Harness 的工具日志和原生 `tool_addition` 延迟定义路线。
- 停用工具：沿用框架权限撤销，保留定义，拦截已停用调用。实际 API 对 `tool_removal` 返回 422，因此不声明已接入原生工具移除。
- 消息队列继续使用现有 Harness 线路。

主插件补丁 `cordis.patch.yml` 配置上述路线；独立 `in-history.patch.yml` 供已有部署更新原生模型能力。`modelRoute` 在 `adapters/harness/framework/request-route.js` 经官方 `agent/request` waterfall 应用，仅作用于此 DataNet 网络。该配置覆盖网络内 Agent 的模型选择；未配置时沿用原请求模型。更换模型应修改或移除 `modelRoute`；能力取决于所选提供者及模型。子 Agent 循环、系统投影、动态工具投影、压缩与请求序列仍由 Harness 实现。

## 内容位置

| 内容 | 当前位置 |
| --- | --- |
| 角色职责、固定网络规则、讨论成员身份 | 稳定系统提示 |
| AGENTS、项目说明、Skill | 按需进入普通历史；标记被压缩后下次需要时加载 |
| 通讯录、管理者、经验、下属反馈、未解决问题记录 | 每项内容变化时加入普通历史；复用已有文档标记机制 |
| 讨论请求计数、待回复消息、当前排障阶段与尝试数 | 每次请求的短尾部 |
| 公共笔记 | 最新正文的请求尾部，沿用同轮共同快照 |
| 协作状态 | 阶段、成员、有效认领、候选 ID、批准成员、验收路径、最近 5 条记录的 160 字符预览 |

协作完整任务仍在任务消息，候选和共享记录全文继续持久化，通过 `datanet_team_status` 读取。`query` 可填写记录 ID 或关键词。摘要不修改存储内容。

## 实测

前置原生能力探针：14 次 API 请求（含 1 次被拒绝的移除请求），4 次系统替换语义测试全部通过（off 两次、high 两次）；新工具正确读取隐藏在新增定义中的参数。长前缀测试系统更新命中 3456 token，工具新增命中 3840 token。工具移除被服务端以 422 拒绝。

证据：`build/native-update-probe/evidence-1791948258984/result.json`。该探针未经过 DataNet 后端，因此另做以下部署通路验证。

更新后的 DataNet 适配器、已编译后端、官方 SDK 提供者与真实 API：3 次付费请求。根原选项为旧兼容路线，由部署 `modelRoute` 切到原生路线。首次 READY，半途修改系统并新增工具，模型按新规则调用新工具，正确使用只存在于工具定义中的参数，最后返回工具结果。

| 请求 | 未命中输入 | 命中输入 | 输出 |
| --- | ---: | ---: | ---: |
| 首次建立前缀 | 9399 | 0 | 2 |
| 更新系统并新增工具 | 1518 | 9344 | 47 |
| 工具结果后续请求 | 176 | 10752 | 7 |
| 总计 | 11093 | 20096 | 56 |

后两次请求输入命中率 92.23%；这是最小通路测试，不是整网缓存收益预测。真实 API 请求体确认前置 system 不变，新系统和 `tool_addition` 位于后续消息，新工具 `defer_loading=true`，带官方动态工具 beta 头。

证据：`build/test-data/creation-VAqi6G/evidence.json`；脚本 `tests/native_cache_route_live_test.cjs`，仅 `DATANET_LIVE_TEST=1` 时执行，最多 3 次付费调用，需要环境凭证。测试将思考关闭、输出上限 512 控制费用；部署默认仍为 high / 50000。

本地验证：3 项缓存位置合同、5 项文件认领、4 项指南路由、5 项应用通信和排障测试通过。真实安装的 Harness + 模拟模型验证了路由覆盖、历史系统追加、原生工具新增，以及停用工具仍声明但调用被拒绝。未运行完整付费端到端测试。

## 官方实现参考

- [历史系统提示替换](https://github.com/deepseek-ai/deepseek-harness/blob/master/.agents/notes/implemented/feature/2026-09-02-in-history-system-prompt-replacement.md)
- [动态工具更新](https://github.com/deepseek-ai/deepseek-harness/blob/master/.agents/notes/implemented/architecture/2026-09-20-dynamic-tool-updates.md)
- [DeepSeek 原生提供者](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/llm/llm-deepseek/README.zh.md)
