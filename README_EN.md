# Nexarbor · 织林

**Turn ideas into networks, and networks into applications.**

Nexarbor is a visual platform for building general-purpose Agent applications. Drag Agents, modules, tools and data onto a canvas, configure their connections, and ask maker Agents to extend or revise the application in natural language.

![NPC town workbench](docs/images/nexarbor-town-workbench.png)

The same framework supports discussion groups, decentralized collaboration, knowledge archives and an NPC town. Reusable modules, local subnodes, explicit access boundaries and configurable frontends keep application structure understandable as it grows. The core, communication layer and frontend have separate responsibilities; Agents run through DeepSeek Harness.

## Install 0.8

- Windows x64 and Git for Windows on PATH.
- Install [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) and authorize your DeepSeek account there. The current native adapter targets the 0.2.0-rc.2 SDK series.
- Download `Nexarbor-0.8.0-win-x64.zip` from [Releases](https://github.com/kazari-qwp/Nexarbor/releases/tag/v0.8.0), extract the entire archive, then run `Nexarbor.exe`.

The archive includes Electron, Python and base dependencies. Local vector retrieval dependencies and model weights are installed on demand. See [installation and assembly](docs/INSTALLATION.md) for Harness paths, credentials and source builds.

## Projects and assembly

Create or open a project folder. Download modules and tools from the resource library into that project, drag them onto nodes, and configure their frontends. Dependencies load recursively and duplicate mounts are avoided. Validate and update the network to apply edits; **Commit** records versions using real Git.

Nodes, tools, modules and whole subnetworks can become reusable bookmarks or presets. Each project owns its resource implementations, network files, data and saved context positions. Copying an Agent creates a fresh conversation.

The independent Python Agent executor and earlier plugin distribution have been retired. The desktop workbench requires DeepSeek Harness.

[中文完整说明](README.md) · [Architecture](docs/ARCHITECTURE.md) · [Module API](docs/LOCAL_MODULES.md) · [Release notes](docs/RELEASE_NOTES_v0.8.0.md)
