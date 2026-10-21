# 用四路输入装配上下文

复用 `context.assembler`。文本节点直接提供正文，无需安装 `context.text`。角色可以本地调用自己的组装器；需要独立资料出边时，将组装器放在角色的亚节点中，通过 `execution.prepare` 明确引用它。

四种类型分别使用独立频道，不把它们合并后遍历：

| 类型 | 默认频道 | 用途 |
|---|---|---|
| system_prompt | context.assembler.system_prompt | 人格、系统规则快照 |
| context | context.assembler.context | 长期资料，正文变化时更新 |
| inputs | context.assembler.inputs | 按稳定身份投递的一次性事件 |
| tail | context.assembler.tail | 每次准备时重读的当前快照 |

每种频道都可配置为列表并选择黑白名单。沿对应频道可达的文本无条件纳入，不通过人物字段、`when` 或 `bindings` 再筛一遍。只连接适用资料；状态改变后，由负责该状态的业务模块增删对应资料连接。

## 来源与顺序

- 普通文本节点：直接读取正文，保留 `ctx.network.nodes()` 的去重广度顺序；需要先后关系时通过连接层次表达。
- 直接来源：在 `sources` 中声明 `id`、`kind`、`type: text` 和 `text`，保留列表顺序。
- 文件来源：在 `sources` 中声明 `type: file` 与 `path`，经明确的文本文件接口读取；路径相对项目，额外目录需显式配置。
- 串联：默认用 `context.assembler` 频道，遍历 `await ctx.network.nodes(channels=[...])` 的节点对象表；直接检查 `node.modules`，按广度顺序调用该节点组装器的 collect 合并其自身来源。

当前组装器先纳入直接/文件来源，再读取各类文本，最后合并下游组装器。相同类型与来源只保留首次结果。不按 `order`、节点 ID 或全局距离重新排序，也不递归提前插入更深层组装器。串联频道也可配置列表和匹配模式。

普通文本的 inputs 来源默认投递一次；直接来源可以填写 `event_id`，并选择 followup / steer。来源身份参与事件 ID，相同事件不重复投递。长期正文更新应使用 context 或 tail；需要再次投递的新事件应有新事件身份。迁移来源时保留已投递记录，避免重发开场白。

## 应用示例与验证

### 执行器的公开输入契约

`execution.prepare` 指向一个公开操作，执行器调用后接收 `data` 中的 `format: nexarbor-context/v1` 与 `patch`。patch 的形状是：`system_prompt: 字符串`、`context: [{id,text}]`、`inputs: [{id,text,delivery}]`、`tail: [字符串]`；delivery 为 followup 或 steer，缺省 followup。可以另带 `errors` 记录来源错误。组件返回数据，执行器负责更新目标 Agent，组件不必越权写父节点输入。

一次性事件由宿主按来源及事件 ID 去重、确认投递并持久化；不要在预览时改投递状态。同一事件 ID 的正文不能改变；更新长期正文用 context/tail，新的事件用新身份。

普通文本直接通过已到达对象的 node.read 读取，不逐节点重新查询可达范围；接口见 02-network。直接磁盘文件可使用官方只读端口 `runtime:read_text`：先用 `catalog_ports` 确认宿主已安装，节点显式提供该引用，模块沿 `runtime.text` 频道 invoke，参数 path 与可选 roots，返回 text/path。装配及测试见 14-host-ports。旧的 `ctx.extended('read_text',...)` 仅给官方组装器，用户组件不能因用了同名 ID 获得它。没有端口时报告能力缺口，不能用 pathlib/open、反射或测试探针绕过 ctx。

当前小镇初始样板的组装器装在居民本节点，工具收集器在独立亚节点；实际装配见13的节点路径。`world.time` 更新本节点时间文本，组装器沿 tail 频道直接读取；怀孕成功后由居民楼接入怀孕资料，生产后由医院切换为育儿资料。组装器无需认识日期、性别、职业和怀孕业务。

避免把人格、记忆、地图、活动和时间查询塞进同一个准备模块，也不要为了读取普通文本增加一层必装模块。通用组装器负责装配，业务模块负责改变状态和关系。

验证普通文本无配套模块也能读取、四类频道隔离、连接决定纳入范围、广度顺序、直接文字/文件、串联去重与环路终止，以及事件不重放。纯读取不额外增加业务事务锁。更多前后对照见 [小镇应用演进](13-town-evolution.md)。
