# 统一接口与频道授权

网络格式 v6。节点只有一组 `interfaces`，JSON 保存为 `connections.interfaces`；不再区分读接口/写接口，也没有工具调用的 direction 参数。来源到目标的方向、private/public、门槛、倍率和扩展属性继续存在。v3/v4/v5存档拒绝读取，不提供兼容转换。

```python
actor.connect('document',channels=['access.read'],visibility='private')
store.register_tool('trade',trade,description='交易',parameters={'type':'object'},access_channels=['market.trade'])
actor.connect('market',channels=['market.trade'])
```

`Node.connect` 只合并目标、可见性、门槛、倍率和属性都相同的授权，频道取并集；仍可用 Interface 表达不同路由参数的平行连接。空频道不授权远端访问。

## 数据、工具与信号

标准数据读取固定使用 access.read，写入固定使用 access.write。公开工具在可信注册处声明 access_channels，省略时 read_only 工具默认 access.read，其余默认 access.write。read_only 保留为效果描述；显式声明能力频道可以覆盖默认值。

发现、装配与每次调用都按目标工具声明检查路径。模型无需填写频道，也不能通过 invoke_tool 参数追加频道。一个只有 world.tick 与 access.read 的连接不能调用需要 access.write 的工具；信号的频道不会变成工具执行权限。Agent 私有工具和 Skill 不因建立连接而公开。

请求携带的频道集合沿路径保持原样，每个接口有任意交集才允许通过。嵌套调用继承剩余强度、频道和去重集合，不能升级。private 只允许所属来源节点直接访问，外部不能通过中继借用；public 仍需满足频道和强度。目标散度调整后强度为负时不进入目标，修复了旧实现多走一跳的问题。

信号使用同一组接口，仍只沿 public 连接按频道重叠逐层传播。Signal 不再携带 direction；同层并行和整层屏障、去重和回源语义保持不变。

## 结构与界面

概况查询可以选择 channels，但不会授予调用权限；工具发现没有调用者自选频道。编辑器局部视角按各工具的可信声明分组计算范围，结构筛选只影响显示。管理工具仍按管理范围授权，接口编辑参数为 interface={metadata:{...}} 或 changes={metadata:{...}}。

三个应用的源码预设和组件已切换为统一连接。知识库组织中间节点不消耗强度，以保留根到具体存储集合的授权范围。讨论公共笔记使用普通文本与 node_write，轮初快照由讨论组件提供；通用文本层不再承担旧 resident_text 特例。
