# 位置资料

程序标识：`place.info`。可装在地点与 Agent 上，提供地点说明、访客和当前位置。

- `read` 返回本地资料，允许通过 `movement` 或 `info` 频道访问。`movement` 沿用道路／移动关系的读取方式；`info` 是独立的只读关系频道，供家庭等内部组件在不伪装成道路的情况下读取真实位置。
- `arrive`／`leave` 只允许通过 `movement` 频道调用，并且只允许修改框架确认的请求发起者自己的访客记录。
- `set_location` 只允许通过 `movement` 频道调用，只更新发起 Agent 自己的当前位置与输入说明，调用来源必须为新地点。

## 可选：从出边派生访客

配置项 `visitors_from_edges` 默认 `false`，保持上面的原有访客记录模式。普通地点节点可把它设为 `true`，让 `read` 的 `visitors` 改为从本节点**自己的出边**派生：只选 `metadata.attributes.relation` 为 `location` 且 `metadata.channels` 含 `movement` 的边的 `target_node_id`，去重后排序。

- 出边是事实来源，返回的 `visitors` 是辅助索引；`read` 返回值与同步发布的元数据始终使用同一份当前派生结果。
- 开启后不读取、也不合并 config/state 里的旧 `visitors`；删除位置边后旧记录不会残留，新增位置边后下一次读取立即可见。
- 不做全图扫描，不读取其他节点的 state；`arrive`／`leave` 仍要求 `movement` 频道并核验真实请求者。
- 只适合普通地点节点。若在 Agent 节点上开启，所有操作都会明确拒绝，避免把 Agent 自己的目的地误当成访客。
- `read` 的访问频道仍为 `movement`／`info`；`arrive`／`leave`／`set_location` 仍只允许 `movement`。

`info` 频道只放宽 `read`，不会授予 `arrive`、`leave` 或 `set_location` 的修改能力；所有请求者身份检查保持不变。组件默认访问配置仍为 `movement`，装配方如需通过 `info` 读取，应在该模块实例的访问配置中显式加入 `info`，不要把家庭等内部关系改名为道路，也不要扩大其他模块的运行授权。

地点填写 description；NPC 填写初始 location，旧地点可填写初始 visitors。常用默认值为空；不扫描全图，不读取外部文件。配合“移动到此”在节点锁内调用，失败由核心回滚。
