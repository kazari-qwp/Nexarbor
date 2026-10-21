# 纯频道接口与工具授权

当前核心网络格式为 **v8**。连接保存在 `connections.interfaces`；普通节点和亚节点分别维护自己的出边。频道及匹配模式控制访问，没有隐含读写、公私分类，也不按工具名称推断权限。

## 连接与传播

```python
actor.connect('store', channels=['documents'], threshold=0, multiplier=1)
```

接口元数据只有 `channels`、`threshold`、`multiplier`、`attributes`。连接仍有来源到目标的方向；移除的是“读取/写入”类别，双向连接仍需分别建立。`connect` 仅合并目标、门槛、倍率和属性相同的连接，频道取并集。

白名单接口要求请求/信号频道与配置集合有交集；黑名单反向过滤。满足频道条件、门槛和强度预算时才能通过。频道全程原样携带，不因经过接口而消耗或替换。`private`、`public`、`documents` 都只是普通字符串；同时携带 public/private 可以有意跨越两类连接。空频道不能到达远端。省略概况查询的频道时只返回自身。

调用和信号使用同一频道、阈值和倍率规则。可达对象按广度顺序返回，不额外重排。信号按广度逐层、同层异步并行；汇聚由目标节点选择 sum/max/min/mean，默认sum。信号下一层使用当前拓扑，普通调用也按调用时的网络检索。

## 工具声明决定能力

```python
store.register_tool('trade', trade, description='交易',
                    parameters={'type': 'object'},
                    access_channels=['market'])
store.expose = ['trade']
actor.connect('store', channels=['market'])
```

注册公开工具必须显式提供 `access_channels`。同一个频道可以开放查询和修改，也可以给不同工具分配不同频道；工具名不影响判断。`expose` 决定节点向外提供哪些工具，频道和强度决定谁能到达它们。Agent 私有工具与已装配工具箱的授予机制仍保留，连接不会把私有工具变成公开服务。

发现、装配和每次调用都按目标工具的可信声明检查路径。调用方不能通过工具参数扩大授权，信号也不能改变工具声明。模块发起的网络请求受自身 `access` 限制；被调用模块运行后使用自己的装配授权，显式转交的请求仍受相应预算约束。管理归属、创建与委托授权分别检查。

## 数据操作

普通模块先用 `nodes = await ctx.network.nodes(channels=[...])` 一次取得可达节点对象，再用 `await node.read(request)`、`await node.write(key,value)` 或 `await node.call(module,operation,args)` 直接操作对象；读取 node.tools/modules/metadata/edges 不再寻路。独立的 `ctx.network.read(target,...)` 仍可单独使用，已持有对象时无需再调用。`await ctx.nodes` 在当前回调复用默认范围；显式 nodes 查询使用当前拓扑。本地 `ctx.read/write` 只作用于所在节点。没有隐含网络级“读/写权限”分类。

普通文本可配置 `tool_channels={'read':['documents'],'write':['editing'],'get_schema':['schema']}`；省略项为空频道，仅本地可用。还须在 `expose` 中显式开放所需工具。`get_schema` 由宿主的 `attach_local_tools` 装配，读取和写入工具由文本节点提供。配置随网络保存和恢复。

## 结构与编辑器

概况查询可以选择频道，不会授予调用权限。工具发现和调用根据声明自动选择频道。接口管理采用 `interface={metadata:{...}}` / `changes={metadata:{...}}`；管理工具的外部目标可达检查使用宿主配置的 `channels`，没有隐含读写频道。

画布使用高对比度线色帮助分辨连接起点，筛选只影响显示。频道表以条目和加号编辑，可以切换黑/白名单。亚节点的归属虚线不是业务边；是否借用父出边、是否向父开放出边分别由核心开关控制。
