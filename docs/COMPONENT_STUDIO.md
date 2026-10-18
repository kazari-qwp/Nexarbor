# 客户端组件工作室

当前使用 `nexarbor-module/v3` 固定异步入口，网络配置为 v8。默认桌面工作区为 `build/workbench-v3`。旧小镇、旧应用、旧发布组件和旧测试预设尚未迁移，未添加兼容层。

1. 打开 Nexarbor 桌面工作台。节点“工具”页可从本机 Harness 官方目录添加工具，设置提供频道；应用网络后生效。
2. Agent 属性中启用 Harness 执行器，设置 strength 和 channels。Agent 沿连接调用 `network_visit`，取得可达节点提供的工具；每次执行会重新检查权限。
3. 打开“组件工作室”，选择“从空白制作组件”或“标准 v3 组件”。使用 CodeMirror 查看、编辑源码和差异。
4. 连接已运行的 Harness 后，可将需求交给组件制作 Agent；它使用原生会话和编码工具，会话可在 Harness 列表中查看。也可以手工修改组件。
5. 验证在独立 Python 子进程运行，有时间和输出上限；校验清单、固定入口、挂载、信号响应、状态和组件自带测试。
6. 通过后才可发布，发布内容必须与已通过验证的源码摘要一致。修改代码后必须重新验证。发布版本只读，可以建立修改副本。
7. 选择节点并装配。示例的 state/access 会保留；主界面的模块页可以查看配置、网络访问授权和状态。组件之间通过公开操作复用，不拿其他实例引用。

制作会话支持继续或分叉历史；指南前缀变化时应开新会话。固定入口和本地 API 见 [组件说明](LOCAL_MODULES.md) 与 [制作指南](../extensions/development/capabilities/component_studio/resources/MODULE_GUIDE.md)。

制作 Agent 的职责、核心 API 和页面协议统一使用中文说明，保留代码标识和协议字段。每次开始制作时工作副本刷新三份当前规范；规范或依赖接口变更后，旧历史不能继续或分叉。测试文件必须由 unittest 实际收集运行，零项收集不会被当成业务验证通过。

## 模块自己的配置页面

组件可在清单中声明 `"frontend":{"entry":"ui.html","title":"元数据字段","height":460}`。页面作为组件源码的一部分验证、发布、导出，修改后必须重新验证。当前使用自包含 HTML，脚本和样式放在页面内；没有页面的组件继续使用 JSON Schema 通用表单。

选择节点，进入“模块”，展开模块即可使用它的页面，也可切换到通用表单。页面通过 `NexarborModule` 获得本模块配置和状态的副本，提交的新配置经过 Schema 校验后进入网络草稿，点击“应用网络”生效。它不能调用任意后端 RPC、修改网络授权或读取其他模块。iframe 使用独立来源沙箱，宿主令牌不会交给页面。

组件工作室支持编辑 `.html/.css/.js`，并提供“页面预览”；发布版本仍只读。详细接口和中文界面要求见 [页面开发规范](../extensions/development/capabilities/component_studio/resources/FRONTEND_GUIDE.md)。

开发组件库附带由真实制作 Agent 编写的 [metadata.fields](../extensions/module_frontend_demo/capabilities/metadata_fields/README.md)：点击“＋ 添加元数据”增加名称、类型和值，支持删除字段，以及字符串、数字、布尔、对象、数组和空值。字段在 `read` 操作或 `metadata.refresh` 信号执行时发布到本节点的模块元数据命名空间。Python 与 HTML 均原样导出，来源摘要见组件内 `provenance.json`。

## 本机 Harness 安装路径

工作室优先使用 `DATANET_HARNESS_EXE` 环境变量；其次读取项目本地、未入库的 `build/harness-installation.json`，格式为 `{"executable":"E:/dsh/Harness/DeepSeek Harness.exe"}`；都没有时采用 Windows 默认安装目录。SDK 从所选程序自身的安装目录加载，避免新版程序混用旧 SDK。测试客户端使用独立 `DSH_HOME` 和界面数据目录，临时文件保存在项目的 E 盘 build 下，不改日常客户端或全局 TEMP/TMP。

“整理当前视图”只根据当前可见节点和连线整理布局；“整理选中”用于选定部分。筛选和普通拖动不会自动触发全图整理。

外部工具与节点组件分开。当前适配的是官方文件、搜索、PowerShell 和后台任务服务，共十个工具；目录和工具测试不需要模型密钥。真实 Agent 对话与组件制作仍使用用户连接的 Harness。通用 MCP/Skill 导入和旧应用迁移以后处理。

验证子进程和模块接口边界不等于恶意代码沙箱。组件源码按可信本地代码运行，外部工具按宿主权限执行。

本轮实际桌面测试已走通：选择官方工具、应用、访问取得、调用读取、断开后拒绝、v3 模块验证／发布／挂载，以及重启恢复。没有付费模型调用。旧小镇的历史测试记录继续保留，但不代表它已在当前协议下复测。
