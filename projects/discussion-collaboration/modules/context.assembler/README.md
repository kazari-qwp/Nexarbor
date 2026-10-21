# 上下文组装器

`context.assembler` 是普通模块，可装在节点或亚节点上。需要独立资料出边时放在亚节点；没有独立出边需求时直接装在本节点。角色通过 execution.prepare 显式调用 assemble，由执行适配器更新四路输入。

四类频道默认是 context.assembler.system_prompt、.context、.inputs、.tail。每种独立遍历，可配置频道列表及黑白名单。沿对应频道可达的普通文本节点无条件纳入，不要求 context.text，不再支持 when、bindings 或 order 过滤排序。动态状态由业务模块增删资料连接表达。

## 来源与顺序

1. sources 中的直接文本（type:text）或文件（type:file）按配置列表顺序纳入。
2. 各类文本节点保留 ctx.network.nodes 的去重广度顺序；用连接层次控制先后。
3. 沿 channels（默认 context.assembler）找到的下游组装器按广度顺序逐个合并自己的来源。调用 collect，不递归提前插入深层来源；来源按类型与稳定 ID 去重，转交剩余强度。

文件路径相对当前项目，每次读 UTF-8；document_roots 可显式允许额外目录。需要官方 read_text 扩展；越界、缺失、编码或大小错误列入来源错误。来源必须有稳定 id 和 kind，具体 Schema 见 module.json。

system_prompt 是系统快照，context 是正文变化时更新的资料，tail 每次重读。inputs 是一次性事件：普通文本默认按来源投递一次，直接来源可指定 event_id 和 followup/steer。相同事件身份不重放；新的事件使用新的身份。

prepare 可以引用本节点或同一归属树内的组装器，不要求普通业务边；外部节点仍须可达。组装器自身读取沿自己的强度和频道授权。预览与 assemble 同源，只读展示四路结果、来源及错误，不消费事件。

组装器不管理记忆、地图、活动或时间。小镇的 world.time 只更新本节点时间正文，组装器沿 tail 读取它；怀孕和育儿文本由业务模块调整连接。完整样板：<安装目录>/resources/examples/npc-town/。
