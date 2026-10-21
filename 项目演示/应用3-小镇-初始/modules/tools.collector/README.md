# 工具收集器

tools.collector 是普通 v3 模块，能装在普通节点或亚节点。新装配示例使用专有频道 `tools.collector`，config.channels 可配置列表和黑白名单；旧配置省略该字段时仍沿用 tools。

`collect({})` 沿配置频道枚举可达的工具，并通过核心 endpoint 查询串联其他收集器，保留调用者身份。按原始提供节点与工具引用去重，优先直接访问和较短收集链。调用链重复出现的收集器会跳过，避免环路。每个收集器使用自己的授权与强度；需要限制转交预算的其他组件可以明确使用 ctx.network.call(...,forward=True)。

`invoke({tool_id,arguments})` 使用最近 collect 建立的目标索引，调用原始工具或转交下级收集器；每一跳仍由核心检查当前频道、距离与工具授权，不重新收集整张工具表；撤销必要路径后旧工具不再生效。可收集宿主工具及模块的 agent_tools，如 module:movement.here/move_here。

推荐把它装到角色的工具收集亚节点，打开 use_parent_links，并把亚节点 ID 加入角色 execution.tool_sources。列表仍属于亚节点；父节点不混入它的模块或工具。检索路径需要允许 config.channels 指定的频道，不要求固定为 tools.collector；小镇直接使用 location/road。实际工具操作仍须授予模块和执行器。

可调范围、频道和业务权限优先改配置，不为每个场所制作新收集器。收集与只读查询不用节点事务锁。核心管理归属、独立出边和开关，模块只调用 ctx.network 接口。

工具发现缓存：state_schema 的 `x-tool-discovery: network` 声明工具表只依赖网络结构、模块配置与工具声明。Harness 适配器仅在这些结构变化后、下一次模型请求前重新收集；业务账本、聊天和时间文本变化不会触发重收集。routes 只保存目标和串联路径，重启时会重新发现；未声明缓存依赖的动态工具提供者保持保守刷新，声明 state 则同时跟踪自身状态。
