# 安装、运行与组件装配

Nexarbor 0.8 是独立的桌面工作台，使用 **DeepSeek Harness 原生运行时**执行 Agent。它以 Windows x64 压缩包分发；请直接运行工作台。

## 安装要求

1. Windows x64，以及已加入 PATH 的 [Git for Windows](https://git-scm.com/downloads/win)。项目的 Commit、修改分支和恢复使用真实 Git。
2. 安装 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)，并在 Harness 内完成 DeepSeek 账户授权。当前适配以 `0.2.0-rc.2` 系列原生 SDK 为基线。
3. 下载 Release 中的 `Nexarbor-0.8.0-win-x64.zip`，完整解压到可写目录，然后双击 `Nexarbor.exe`。压缩包包含 Electron、Python 和基础依赖，无需另装 Node.js 或 Python。

首次启动提供“打开项目文件夹”和“新建项目文件夹”。新建会准备 Git 仓库、资源目录和 `打开项目.cmd`。以后可直接双击项目中的脚本。

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

## 资源与装配

- 从工作台新建项目，或打开已有的 `nexarbor.json` 所在文件夹。
- 资源库中的模块、工具通过条目旁的下载箭头安装到当前项目。模块源码保存到 `modules/`，工具声明保存到 `tools/`；递归依赖会一起装配。
- 把模块或工具拖到节点上会补齐所需能力并去重。配置好后点击“校验并更新网络”，使编辑内容进入运行网络；点击 **Commit** 保存项目版本。
- 节点、模块和网络都能保存成书签。网络预设以真实网络文件保存；可重复单元数量由预设声明，在右侧填写后拖入即可展开。
- 完整网络保存在 `network_presets/networks/`，零件预设保存在 `network_presets/fragments/`。项目自己的资源与版本随项目文件夹管理。

三个示例的初始网络在 `configs/` 中。使用“工作台 → 打开应用配置”选择对应的 `profile.json`，可以在独立示例工作区体验；正式项目请将使用的资源下载到项目目录后 Commit。

## 按需安装向量检索能力

基础运行包提供画布、普通模块、文本、JSON、CSV、SQLite 和图片地图所需依赖。向量检索和本地嵌入模型按需准备，模型权重不随运行包分发。

需要本地 RAG 时，在解压目录执行：

```powershell
.\runtime\python\python.exe -m pip install -r .\extensions\storage\capabilities\llamaindex\requirements.txt
```

该步骤会安装相应的嵌入依赖并可能下载模型；建议把模型缓存放到空间充足的磁盘。节点缺少可选依赖时会在客户端显示错误，项目网络仍可打开。

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
