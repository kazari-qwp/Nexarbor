# 纯频道接口与工具授权

当前核心网络格式为 **v7**。每个节点只有 `interfaces`，保存为 `connections.interfaces`。核心不再内置读/写、公有/私有分类，没有 `visibility`、`direction` 或 `read_only` 参数，也不按工具名称推断权限。旧格式直接拒绝，不提供兼容转换。本轮不迁移旧组件、预设及三个应用；这些目录中的旧参数不能用于当前核心。

## 连接与传播

```python
actor.connect('store', channels=['documents'], threshold=0, multiplier=1)
```

接口元数据只有 `channels`、`threshold`、`multiplier`、`attributes`。连接仍有来源到目标的方向；移除的是“读取/写入”类别，双向连接仍需分别建立。`connect` 仅合并目标、门槛、倍率和属性相同的连接，频道取并集。

请求或信号的频道集合与接口频道有任意交集，且满足门槛与强度预算时，才能通过。频道全程原样携带，不因经过接口而消耗或替换。`private`、`public`、`documents` 都只是普通字符串；同时携带 public/private 可以有意跨越两类连接。空频道不能到达远端。省略概况查询的频道时只返回自身。

同步访问和信号传播使用同一频道规则。信号仍按广度逐层执行、同层并行并等待整层结束；信号汇聚取最大强度，普通访问沿用既有强度汇聚。两者都保留倍率、目标散度、去重和执行预算。

## 工具声明决定能力

```python
store.register_tool('trade', trade, description='交易',
                    parameters={'type': 'object'},
                    access_channels=['market'])
store.expose = ['trade']
actor.connect('store', channels=['market'])
```

注册公开工具必须显式提供 `access_channels`。同一个频道可以开放查询和修改，也可以给不同工具分配不同频道；工具名不影响判断。`expose` 决定节点向外提供哪些工具，频道和强度决定谁能到达它们。Agent 私有工具与已装配工具箱的授予机制仍保留，连接不会把私有工具变成公开服务。

发现、装配和每次调用都按目标工具的可信声明检查路径。调用方不能通过 `invoke_tool` 填写频道扩大权限；触发信号也不能改变工具声明。嵌套调用继承剩余强度、频道和去重集合，不能扩大频道集合。管理归属、创建与委托授权仍分别检查。

## 数据操作

`Network.read/write` 与 Backend 的 read/write RPC 已删除。远程数据操作统一走 `list_tools` / `invoke_tool`。本地 `Node.read`、`TextFileNode.read/write` 是存储实现，不再代表网络级特殊权限。

普通文本可配置 `tool_channels={'read':['documents'],'write':['editing'],'get_schema':['schema']}`；省略项为空频道，仅本地可用。还须在 `expose` 中显式开放所需工具。`get_schema` 由宿主的 `attach_local_tools` 装配，读取和写入工具由文本节点提供。配置随网络保存和恢复。

## 结构与编辑器

概况查询可以选择频道，不会授予调用权限。工具发现和调用根据声明自动选择频道。接口管理采用 `interface={metadata:{...}}` / `changes={metadata:{...}}`；管理工具的外部目标可达检查使用宿主配置的 `channels`，没有隐含读写频道。

画布使用频道集合生成颜色，不再提供公私选择框或私有虚线。筛选只影响显示。前端本轮使用无 Agent 运行的五节点样例验证布线；旧应用后端尚未迁移，详见本轮实施与验证（本地开发资料：`ROUTING_CHANNELS_V7_TEST_20261017.md`）。
