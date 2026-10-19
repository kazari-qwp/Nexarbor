# 工具收集器

tools.collector 是普通 v3 模块，能装在普通节点或亚节点。新装配示例使用专有频道 `tools.collector`，config.channels 可配置列表和黑白名单；旧配置省略该字段时仍沿用 tools。

`collect({})` 沿配置频道枚举可达的工具，并通过核心 endpoint 查询串联其他收集器，保留调用者身份。按原始提供节点与工具引用去重，优先直接访问和较短收集链。调用链重复出现的收集器会跳过，避免环路。每个收集器使用自己的授权与强度；需要限制转交预算的其他组件可以明确使用 ctx.network.call(...,forward=True)。

`invoke({tool_id,arguments})` 按当前网络重新收集并检查，再调用原始工具或转交下级收集器；撤销必要路径后旧工具不再生效。可收集宿主工具及模块的 agent_tools，如 module:movement.here/move_here。

推荐把它装到角色的工具收集亚节点，打开 use_parent_links，并把亚节点 ID 加入角色 execution.tool_sources。列表仍属于亚节点；父节点不混入它的模块或工具。道路和移动后新位置连接都需带 tools.collector；实际调用业务操作的频道仍须授予模块和执行器。

可调范围、频道和业务权限优先改配置，不为每个场所制作新收集器。收集与只读查询不用节点事务锁。核心管理归属、独立出边和开关，模块只调用 ctx.network 接口。
