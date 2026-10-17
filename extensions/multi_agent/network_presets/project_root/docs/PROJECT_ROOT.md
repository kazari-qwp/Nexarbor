# 项目根网络配置（0.2.7）

## 配置位置

标准网络包：backend/host_configs/project_root/package.json。
独立 Agent 包：backend/host_configs/project_root/agent/package.json 和 prompt.md。
网络包旁的 project.md、progress.md、work.md 是实例初始文本模板。

网络采用已有 kind=network/version=1 配置包，内部为 JSON v6 节点和接口。root 是入口节点，引用 project_root Agent 包，连接 root/project、root/progress、root/work 三个文本节点；接口为 private、threshold=0、multiplier=1，频道为 access.read 和 access.write。工作子节点和子网络在任务执行中挂到根节点上，不在初始配置中硬编码。

## 加载与权限

用既有 load_network_package(...).instantiate() 或 mount() 可以装配这份网络。传入 storage_dir 时，框架通用资源装配将文本模板、Agent 提示词和工具定义复制到独立实例目录；不修改组件包，同一模板的不同实例不共享可写文本和提示词。

Harness 使用通用 rootNetwork 配置选择根网络，而不是专用 project_root 初始化分支。rootNetwork 可以是组件 ID、相对后端资源目录的路径或标准网络包绝对路径；rootEntryPoint 默认 root，对应节点 ID 必须为 root。官方根会话绑定这个根节点，读取该节点 Agent 配置中的提示词。它不会额外创建第二个项目根 Agent，也不启用 Python Agent 循环。

完整宿主 config 示例为 host_configs/project_root/harness.config.json，包含 rootNetwork、workspace、storage、创建权限、信号上限和工具能力档案；这是插件 config 内容，不是完整 Cordis patch。网络/Agent 配置负责拓扑和职责，Harness 宿主 config 决定实际工具及创建权限，模型不能凭网络配置扩大授权。官方工具申请 read/write/edit/glob/grep/bash/pwsh/skill，缺失工具不会凭空提供；Skill 白名单默认为空。

默认不加载根网络，现有客户端配置未改。每个用户项目采用独立 workspace/storage。已有检查点优先，启动时不以模板替换正在工作的网络。私有接口是遍历边界，官方文件工具仍由 Harness 工作区与审批约束。

## 通用实现及验证

删除旧 init_project_root RPC、rootPreset 选项及 presets/project_root 启动预设。标准 NetworkPackage 支持通用实例资源目录，节点创建工具挂载网络时也使用该机制隔离资源。没有按项目文件名初始化节点或拼接接口的专用代码。

最小后端检查覆盖标准包加载、四节点和私有接口、两个实例文档与提示词隔离、真实文本写入、重启后保留内容、文档不能读取兄弟节点。未发起真实模型任务，未修改现有客户端安装。


项目根网络和其 Agent 配置仅放在 `backend/host_configs/project_root/`，不放入 Agent 可选组件预设目录，也不注册到预设发现/创建工具。示例 rootNetwork 为 `host_configs/project_root/package.json`。这限制的是预设发现，不承诺对获准的官方文件工具隐藏配置文件。


## 当前源码的工具箱配置

当前宿主示例改为 rootToolboxes/defaultAgentToolboxes/discussionToolboxes/allowedAgentToolboxes；旧能力档案和功能开关不再使用。提示词和文档节点仍属于原标准网络配置。接口管理现已支持新增和删除，详情见 TOOLBOXES.md。本轮不打包，不更新现有客户端。
