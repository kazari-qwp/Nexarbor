# 按组件装配

扩展包负责分发；组件负责加载；应用是一份组件选择清单和网络配置。框架不导入整包实现。

## 目录与依赖

`extension.json` 的 `sources` 指向组件来源目录，`select` 声明应用入口组件。每个组件的 `component.json` 声明唯一 ID、版本、`requires`、资源和实现入口。框架只导入入口及其依赖闭包，按确定的拓扑顺序装配。同一个来源或组件不会重复加载。

```json
{
  "id": "my_application",
  "version": "0.4.0",
  "sources": ["../foundation", "../storage"],
  "select": ["nodes/csv"]
}
```

上述清单只加载 CSV 节点及其实现，不导入 Agent、讨论、Wiki 或向量模型。

依赖可写组件 ID，也可写 `{"id":"nodes/csv","version":">=0.4.0,<0.5.0"}`。当前版本格式为数字 `major.minor.patch`，支持比较约束和逗号组合。缺失、重复 ID、依赖循环及版本冲突均明确报错。

## 选择与停用

```powershell
$env:PYTHONPATH = "$PWD/python"
python scripts/components.py list --root extensions/multi_agent
python scripts/components.py select nodes/csv --root extensions/storage
python scripts/components.py enable nodes/csv --root extensions/storage
```

`select` 保存本地 `selection.json`；`enable` 同时启用必要依赖；`disable` 保存 `profile.json` 中的停用标记。配置在下次启动生效。`DATANET_COMPONENT_SELECTION` 的 JSON 数组可覆盖选择；`DATANET_COMPONENT_PROFILE` 可覆盖开关。

运行时停用组件会级联撤销依赖组件、工具执行和上下文服务。已声明的原生工具定义保留以保护缓存，实际调用由权限检查拒绝。已停用存储组件的节点以休眠记录保存，不导入该组件代码，不删除数据；重新启用后按原类型恢复。缺少组件的未知节点类型明确报错。

组件加载与工具授权分开。加载依赖不增加 Agent 工具权限；工具箱仍须明确装配。应用的默认授权及角色授权由配置声明。

## 当前组合

| 位置 | 用途 |
|---|---|
| `extensions/foundation` | Agent 装配与执行、委托、消息、报告、终端、文本交付、排障、共享 Git 工作区等独立组件 |
| `extensions/storage` | CSV、SQLite、LlamaIndex、llm-wiki、MkDocs 适配等数据组件 |
| `extensions/multi_agent` | 第一应用的讨论、协作、角色及组合清单 |
| `extensions/knowledge_base` | 第二应用的知识接口、主 Agent 与受限助手、归档与查询组合 |
| `extensions/all` | 两个应用共存的显式组合 |

实现代码放在 `capabilities`；节点、工具箱和网络预设保持配置与文档。工具绑定归各工具箱的 `bindings.json` 所有，不再依赖整包工具登记表。

第三方库声明在相应能力的 `requirements.txt`。只有调用相关能力时才导入其可选实现；框架不会下载模型或执行依赖安装脚本。Harness 适配层使用 Python 解析后的原生扩展路径，没有第二套业务依赖解析。
