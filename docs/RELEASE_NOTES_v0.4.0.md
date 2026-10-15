# Nexarbor v0.4.0 — First public release / 首个正式发布

Nexarbor (织林) is a dynamic network framework for data, agents, and capabilities. Multi-agent collaboration is its first implemented application; a networked database and dynamic NPC worlds are planned applications.

## Highlights

- Four independent parts: the core, Harness adapter, optional standalone executor, and multi-agent collaboration extension.
- Core nodes include ordinary nodes, text nodes, and Agent nodes with private Markdown memory.
- Pluggable extensions use node configurations, capabilities, toolboxes, and network presets. Business code lives in capabilities; toolboxes list tool entries with framework-enforced permissions.
- Configurable discussion and decentralized project groups, asynchronous delegation, messaging, reports, shared documents, task claims, Git worktrees, and shared acceptance.
- Persistent network state, detached-network archives, Agent reuse within a root network, member-failure isolation, and bounded terminal jobs.
- Chinese and English project READMEs, architecture documentation, and historical engineering evaluation records.

## Install

Download **datanet-harness-0.4.0.tgz**, import it into DeepSeek Harness, and enable the plugin. Configure the workspace, storage directory, and model route before use. The included backend targets **Windows x64**; integration was verified with Harness **0.2.0-rc.2**.

Python imports and the plugin package retain the `datanet` / `datanet-harness` identifiers. The release includes `SHA256SUMS.txt` for verifying the archive.

## Validation

The architecture refactor passed 90 regression cases with one optional binary case skipped and subsequently checked separately. The additional frozen-module resource check and native integration tests passed. A real-client memory write/read smoke test completed in about eight seconds using three model requests. Historical fixed-network project deliveries and comparison results are documented in the application guide; the full project benchmark was not rerun for this release.

## 中文说明

这是织林 / Nexarbor 的首个正式 release。当前交付为通用网络核心与第一个应用——多 Agent 协作，包括独立会话与记忆、讨论和执行小组、异步委托、报告及协作验收。

请下载附件中的 `datanet-harness-0.4.0.tgz` 导入客户端。运行条件为 Windows x64，已验证 Harness 0.2.0-rc.2。代码和插件技术标识暂时沿用 datanet。数据库与动态 NPC 世界仍在规划中。

旧版本安装包和绑定本机历史目录的一次性脚本已从当前仓库移除；维护中的回归测试和历史评估报告保留。项目许可证尚未确定，相关状态见 README 的 License 部分。
