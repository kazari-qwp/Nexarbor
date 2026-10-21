# 安装、运行与组件装配

Nexarbor 0.8 是独立的桌面工作台，使用 **DeepSeek Harness 原生运行时**执行 Agent。它以 Windows x64 压缩包分发；请直接运行工作台。

## 安装要求

1. Windows x64，以及已加入 PATH 的 [Git for Windows](https://git-scm.com/downloads/win)。项目的 Commit、修改分支和恢复使用真实 Git。
2. 安装 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)，可在 Harness 内完成 DeepSeek 账户授权，也可在工作台配置自己的 API key。工作台使用本机安装的原生 SDK，当前已实测 Harness 0.2.1；0.2.0 缺少必要的原生服务。遇到缺少 SDK 服务的启动错误时请升级 Harness。
3. 下载 Release 中的 `Nexarbor-0.8.0-win-x64.zip`，完整解压到可写目录，然后双击 `Nexarbor.exe`。压缩包包含 Electron、Python 和基础依赖，无需另装 Node.js 或 Python。

首次启动提供“打开项目文件夹”和“新建项目文件夹”。新建或首次打开会准备 Git 仓库、资源目录和 `打开项目.cmd`。以后可直接双击项目中的脚本。

## 连接本机 Harness

默认查找 `%LOCALAPPDATA%\Programs\DeepSeek Harness\DeepSeek Harness.exe`。安装在其他位置时，设置 `DATANET_HARNESS_EXE` 为可执行文件的完整路径。

授权文件可以通过制作 Agent 页面的 Harness home 指定，也可以设置 `DATANET_HARNESS_CREDENTIALS` 为 `.credentials.yaml` 的完整路径。默认依次尝试 `DSH_HOME` 和 `%USERPROFILE%\.dsh`。授权内容只由本机运行器读取，不写入项目或压缩包。

例如，新建一个仅在本机使用的启动脚本：

```bat
@echo off
set "DATANET_HARNESS_EXE=D:\Apps\DeepSeek Harness\DeepSeek Harness.exe"
set "DATANET_HARNESS_CREDENTIALS=D:\HarnessHome\.credentials.yaml"
start "" "%~dp0Nexarbor.exe"
```

## 模型与独立 API 连接

选中 Agent 节点，在右侧“模型”页取消“使用默认模型”，选择服务商连接和模型；点击连接右侧 **+** 可以新增连接，填写名称、服务商、接口类型、Base URL、API key 和模型列表。支持 Chat Completions、Responses 和 Anthropic Messages 兼容接口，实际兼容性以服务商提供的协议为准。模型名可以手动填写，也可查询连接的模型列表。

**同一服务商的不同 key 要建立不同连接。** 每个节点分别保存连接引用；组件／模块制作 Agent 和网络预设制作 Agent 也各有“模型”页。顶部“设置 → 模型与 API”控制当前项目默认值。制作 Agent 的设置点击“保存模型选择”；节点的设置点击“校验并更新网络”生效。修改一条已有连接的 key 会影响使用该连接的所有 Agent；需要独立使用时请新建连接。

API key 使用当前 Windows 账户的 DPAPI 加密，存于 `%LOCALAPPDATA%\Nexarbor\models\`，不放进项目、Commit、网络导出、书签或模型提示词。更换电脑后需重新配置本机连接。切换模型或 key 后，后续运行从当前上下文建立新分支，保留旧历史。无论选择哪种连接，Agent 都由已安装的 Harness 原生 SDK 执行。

## 外部编辑文本

选中文本节点，在“资料”页点击“打开文本文件”，或右键该节点选择同名菜单项。“在资源管理器中显示”会打开所在文件夹并选中文件。默认使用系统关联程序；在“设置 → 外部文本编辑器与快捷键”可填写 VS Code 等编辑器的完整 `.exe` 路径。

项目文本以原始 UTF-8 文件保存在 `context/<网络标识>/` 下，外部编辑器直接打开这份文件。保存后同步到客户端草稿，点击“校验并更新网络”再进入运行网络；Commit 把正文文件及网络一起保存到 Git。若工作台和磁盘同时修改，会显示两份内容供选择。旧版 JSON 文本快照仍可读取。

“资料 → 关联文本文件”也可选择项目外的 UTF-8 文本。外部引用保留绝对路径，运行时直接读取；正文不复制进 Git，也不会随项目回滚。外部文件用文件编辑器修改，客户端显示内容；需要随项目携带时，打开加载后点击“转为项目文本”，再 Commit。复制和书签要求独立资源，外部引用应先转为项目文本。

## 资源与装配

- 从工作台新建项目，或打开已有的 `nexarbor.json` 所在文件夹。
- 资源库中的模块、工具通过条目旁的下载箭头安装到当前项目。模块源码保存到 `modules/`，工具声明保存到 `tools/`；递归依赖会一起装配。
- 把模块或工具拖到节点上会补齐所需能力并去重。配置好后点击“校验并更新网络”，使编辑内容进入运行网络；点击 **Commit** 保存项目版本。
- 节点、模块和网络都能保存成书签。网络预设以真实网络文件保存；可重复单元数量由预设声明，在右侧填写后拖入即可展开。
- 完整网络保存在 `network_presets/networks/`，零件预设保存在 `network_presets/fragments/`。项目自己的资源与版本随项目文件夹管理。

完整小镇学习项目随安装包放在 `resources/examples/npc-town/`，包含网络、文本、模板、模块源码及工具声明。两个制作 Agent 可加载 inspect-network，用 project 指向该文件夹随时按需研究，也能查看任意其他 Nexarbor 项目。若要运行或修改样板，先复制整个目录到自己的项目位置再打开。

示例项目在 `projects/` 中，各自带完整业务模块、工具与数据；请先复制到工作位置再打开。`configs/` 的 `profile.json` 只负责指向普通项目，不再从宿主执行应用专属迁移。框架资源库保留通用能力，商店、移动、家庭、讨论与协作等业务实现在各项目的 `modules/` 内。

## 按需安装向量检索能力

基础运行包提供画布、普通模块、文本、JSON、CSV、SQLite 和图片地图所需依赖。向量检索和本地嵌入模型按需准备，模型权重不随运行包分发。

需要本地 RAG 时，在解压目录执行：

```powershell
.\runtime\python\python.exe -m pip install -r .\extensions\storage\capabilities\llamaindex\requirements.txt
```

该步骤安装嵌入运行依赖，模型权重仍需另外准备，并在节点配置中填写本地模型路径；建议把模型放到空间充足的磁盘。节点缺少可选依赖或模型时会显示错误，项目网络仍可打开。

## 从源码装配

准备 Git、Node.js/npm、Python 3.11 和 DeepSeek Harness，在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
npm install
npm --prefix frontends/network-editor install
npm --prefix frontends/desktop install
npm --prefix frontends/network-editor run build
npm start
```

重建 Windows 运行包：`npm run package`。脚本把干净源码、构建后的前端和必要运行依赖装配到 `build/release/`，生成 ZIP 与 SHA-256 校验文件。测试、历史报告、凭据和运行缓存均不打包。
