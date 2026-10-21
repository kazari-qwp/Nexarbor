# Nexarbor · 织林

**Turn ideas into networks, and networks into applications.**

Nexarbor is a visual platform for building general-purpose Agent applications. Drag Agents, modules, tools and data onto a canvas, configure their connections, and ask maker Agents to extend or revise the application in natural language.

![NPC town workbench](docs/images/nexarbor-town-workbench.png)

The same framework supports discussion groups, decentralized collaboration, knowledge archives and an NPC town. Reusable modules, local subnodes, explicit access boundaries and configurable frontends keep application structure understandable as it grows. The core, communication layer and frontend have separate responsibilities; Agents run through DeepSeek Harness.

## Install 0.8

- Windows x64 and Git for Windows on PATH.
- Install [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) and authorize your DeepSeek account there. The native adapter is verified with Harness 0.2.1; 0.2.0 lacks required SDK services. Upgrade Harness if startup reports a missing native service.
- Download `Nexarbor-0.8.0-win-x64.zip` from [Releases](https://github.com/kazari-qwp/Nexarbor/releases/tag/v0.8.0), extract the entire archive, then run `Nexarbor.exe`.

The archive includes Electron, Python and base dependencies. Local vector retrieval dependencies and model weights are installed on demand. See [installation and assembly](docs/INSTALLATION.md) for Harness paths, credentials and source builds.

## Projects and assembly

Create or open a project folder. Download modules and tools from the resource library into that project, drag them onto nodes, and configure their frontends. Dependencies load recursively and duplicate mounts are avoided. Validate and update the network to apply edits; **Commit** records versions using real Git.

Nodes, tools, modules, Skills and whole subnetworks can become reusable bookmarks or presets. Skills declare dependencies and expose detailed guidance on demand. Consultation and creation share conversations and resume the previous conversation by default. Network views support channel/type/module filters, high-contrast edges and hierarchical or compact layouts. Each project owns its resource implementations, network files, data and saved context positions. Copying an Agent creates a fresh conversation.

Module code receives BFS-ordered reachable node objects from `ctx.network.nodes()`. It can inspect their tool/module tables and use their operations directly without repeating a graph search for each node. Context assembly and tool collection use this API. Running network state is persisted automatically; Git commits separately preserve version history.

The independent Python Agent executor and earlier plugin distribution have been retired. The desktop workbench requires DeepSeek Harness.

[中文完整说明](README.md) · [Architecture](docs/ARCHITECTURE.md) · [Module API](docs/LOCAL_MODULES.md) · [Release notes](docs/RELEASE_NOTES_v0.8.0.md)

## Included projects

These projects accompany the current main-branch source; published archives retain the contents of their respective releases.

Application implementations live in ordinary project folders; the framework library keeps generic modules such as context assembly, tool collection, records, messaging and data access.

- [Preset-based compatibility project](projects/preset-compatibility/): starts with a root Agent and administrator; instantiate discussion and execution groups before the CSV-to-JSON task.
- [Assembled discussion/collaboration reference](projects/discussion-collaboration/).
- [Knowledge archive](projects/knowledge-archive/): starts empty and creates separate CSV, SQLite, RAG and Wiki collection nodes; supports provenance, versions, incremental ingestion and optional local vector search.
- [Agent-rebuilt town](projects/npc-town/) and the [maintained teaching sample](resources/examples/npc-town/), now the new initial-state project with 59 nodes and 19 project-owned modules, included by the packaging pipeline.

Copy a project folder to your workspace and open it in Nexarbor. Opening initializes local Git and a launcher. Configure your own model connection; credentials and old sessions are not distributed. Three functional compatibility runs used DeepSeek Flash:

- Preset-based CSV-to-JSON development passed all 18 historical checks, with every collaboration member approving the same candidate before submission.
- The knowledge application completed archive, query, update, history, restart and semantic-search-to-Wiki-source workflows. Two additional feedback rounds closed remaining ingestion items. Vector trials used a local BGE model; configure your own model directory in the source project.
- The town completed 25 ticks over five days plus restart recovery, without repeating opening inputs.

These results cover the tested workflows and recovery, rather than guaranteeing one-shot success for arbitrary tasks. Test reports, timelines, logs and temporary artifacts remain local. This update also fixes the node-chat blank screen, repeated UUID-based tool deactivation notices, and stale edge routes after switching channel filters.
