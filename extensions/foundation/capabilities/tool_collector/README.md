# 工具收集器

tools.collector 是普通 v3 模块，能装在普通节点或亚节点。默认收集频道为 `tools`；config.channels 可配置列表和黑白名单，也可以显式选择 tools.collector 等专有频道。实际默认值以本目录的 module.json / example.json 为准，不区分所谓新旧配置。

`collect({})` 沿配置频道一次取得按广度排列的节点对象。每个对象先检查 node.modules 并调用其收集器，再读取 node.tools；不逐节点重查路径或工具端点，保留调用者身份。按原始提供节点与工具引用去重，优先直接访问和较短收集链。调用链重复出现的收集器会跳过，避免环路。每个收集器使用自己的授权与强度。

`invoke({tool_id,arguments})` 使用最近 collect 建立的目标索引，调用原始工具或转交下级收集器；每一跳仍由核心检查当前频道、距离与工具授权，不重新收集整张工具表；撤销必要路径后旧工具不再生效。可收集宿主工具及模块的 agent_tools，如 module:movement.here/move_here。

推荐把它装到角色的工具收集亚节点，打开 use_parent_links，并把亚节点 ID 加入角色 execution.tool_sources。列表仍属于亚节点；父节点不混入它的模块或工具。检索路径需要允许 config.channels 指定的频道，不要求固定为 tools.collector。当前内置小镇的工具亚节点 config.channels 为 movement，并通过 use_parent_links 借用居民的位置连接；实际授权以样板节点JSON为准。实际工具操作仍须授予模块和执行器。

可调范围、频道和业务权限优先改配置，不为每个场所制作新收集器。收集与只读查询不用节点事务锁。核心管理归属、独立出边和开关，模块只调用 ctx.network 接口。

工具发现缓存：state_schema 的 `x-tool-discovery: network` 声明工具表只依赖网络结构、模块配置与工具声明。Harness 适配器仅在这些结构变化后、下一次模型请求前重新收集；业务账本、聊天和时间文本变化不会触发重收集。routes 只保存目标和串联路径，重启时会重新发现；未声明缓存依赖的动态工具提供者保持保守刷新，声明 state 则同时跟踪自身状态。
