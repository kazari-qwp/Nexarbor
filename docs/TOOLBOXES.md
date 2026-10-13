# 工具箱清单

每个工具箱位于 `components/toolboxes/<ID>/`。`component.json` 声明启用状态、依赖、实现入口及工具选项；具有 `box` 字段的清单指向自己的 `box.json`。组合工具箱通过 `includes` 引用其他工具箱，Agent 预设声明默认工具箱。

网络业务工具按组件归属登记。官方工具和 Skill 在每个 Agent 的独立作用域装配，宿主授予的能力限制仍适用。停用工具保留 Harness 定义，通过执行权限拒绝调用；重新开放不会重复注册定义。

Python 节点工具箱通过 `python.toolbox_installers` 提供 `register_toolbox` 入口，例如 `toolboxes/local_data`。停用后节点数据与工具定义保留，工具调用返回 forbidden。

使用 `python scripts/components.py list` 查看实际 ID，`disable <ID>` 或 `enable <ID>` 修改 profile，重启 Harness 生效。原子工具箱、组合工具箱与带实现的工具箱使用同一个组件目录结构。
