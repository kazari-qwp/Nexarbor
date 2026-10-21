# 组件装配与项目资源

框架组件根为 `extensions/development`，用 `extension.json` 的 select、sources 选择能力，`component.json` 声明递归依赖与资源。组件实现按需加载，缺失依赖或显式禁用会报错，不静默换用业务实现。

| 位置 | 内容 |
| --- | --- |
| `extensions/foundation/` | 模块协议、执行端口、网络管理员、工具收集和预设展开等通用能力。 |
| `extensions/composable/` | 上下文组装等可组合通用模块；应用模块以具体项目清单为准。 |
| `extensions/storage/`、`extensions/knowledge_base/` | 文本、JSON、CSV、SQLite、Wiki、可选向量数据及通用数据访问。 |
| `extensions/development/` | 两个制作 Agent、渐进式 Skill、独立制作副本、验证与发布。 |
| `extensions/editor/` | 浏览器工作台资源。 |
| `projects/<项目>/modules/` | 该项目的移动、商店、家庭、讨论、协作等业务实现。 |
| `resources/examples/npc-town/` | 独立且完整的内置学习项目。 |

应用通过普通项目清单加载。资源库安装把模块源码及递归依赖放入项目 `modules/`，工具引用放入 `tools/`，Skill 放入 `skills/`；拖入节点后按声明补装依赖。不同项目拥有自己的实现版本，主节点与亚节点的模块、工具列表互相独立。

制作网络时先查模块接口和预设摘要，按需再展开配置、源码与教程。`catalog_presets` 查看当前项目预设，`instantiate_preset` 根据可重复成员数创建草稿并返回新编号映射；其后用 `edit_network` 连接入口。它不自动执行 Agent 或发布网络，正常验证与管理员授权检查仍然生效。

模块 `module.json` 声明操作、配置/状态 Schema、依赖和 Agent 工具；可选前端为 `ui.html`。节点引用以 `format: "node-id"` 声明，复制与预设实例化才能跟随映射。第三方依赖在组件 requirements 中声明，框架不会擅自下载模型。

参见 [模块协议](LOCAL_MODULES.md)、[制作工作室](COMPONENT_STUDIO.md)、[安装指南](INSTALLATION.md)。
