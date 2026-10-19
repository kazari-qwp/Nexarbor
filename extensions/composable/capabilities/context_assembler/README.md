# 上下文组装器

通用普通模块，可装在节点或亚节点上。推荐给角色挂一个亚节点，装 context.assembler，保留独立的出边。角色不用再向每份文本拉线，也不用添加到组装器的业务边。

角色执行设置示例：
```json
{"executor":"harness","strength":2,"channels":[],"prepare":[{"node":"角色的上下文亚节点","module":"context.assembler","operation":"assemble","arguments":{}}]}
```

同一归属树的 prepare 走核心本地调用，不消耗寻路强度或要求频道。普通外部节点仍按可达性访问。组装器自己的读取范围由它的模块强度和授权决定。返回 nexarbor-context/v1 包，由执行适配器更新四路输入，不直接写其他角色的数据。

## 来源与频道

- 文本节点装 context.text，按 `context.assembler.system_prompt`、`.context`、`.inputs`、`.tail` 四类频道分别接线。每类独立遍历，不能借业务频道混合扩散。每个字段可改为频道列表，界面使用加号和条目，并能切换黑白名单。
- 直接文本在 sources 填稳定 id、kind、type:text、text。
- 文件在 sources 填 type:file、path；相对当前项目目录，每次读取 UTF-8。默认不能越出项目，document_roots 可显式授予额外目录。越界、缺失、非 UTF-8 或超过 1 MiB 均报告来源错误。需要示例配置的 read_text 扩展授权，仅原样官方组件提供这个端口。
- `channels` 默认 `["context.assembler"]`，沿此频道找到其他组装器并合并结果。调用链停止环路，来源按稳定 ID 去重；递归调用转交剩余强度，不重置预算。

## 条件与输入语义

when 是等值条件，支持 JSON Pointer。默认事实为本容器元数据；bindings 可显式调用模块只读操作，把结果对象合入事实。`node:"$parent"` 能读取当前父对象，如 records.store.read 的 /values，不硬编码人物编号。本地调用免连线，外部事实来源必须可达且有授权。

system_prompt 是当前系统快照，context 是正文变化才更新的资料，tail 每次请求读取当前文本。inputs 是一次性事件，必须有稳定 event_id；相同事件不重放，同 ID 改正文拒绝。来源按 order、id、kind 排序。输入 ID 包含来源，避免不同组装器的同名事件相互覆盖。

工作台“装配预览”使用草稿配置与当前已校验的连线，展示四路成品、来源、路径、匹配结果和错误。预览只读，不投递事件。移除 prepare 后撤下旧快照，保留历史对话与事件交付回执。

组装器不包含 NPC、时间、地图或私人记忆逻辑。时钟输出是 clock.counter 可配置的普通文本，按 tail 频道接入；记忆、场景查询各用独立模块。教材：docs/CONTEXT_ASSEMBLER_CASE_STUDY.md；核心归属机制：docs/SUBNODES.md。
