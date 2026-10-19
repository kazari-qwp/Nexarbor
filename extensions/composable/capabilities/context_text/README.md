# 上下文文本源

装在文本节点上，只用 ctx.read 读取自己的 content，不探索网络，也不操作任何 Agent。由连线选择 system_prompt、context、inputs 或 tail。配置支持 order、when、enabled；一次性输入还需 event_id，可选 delivery:followup/steer。

配合相邻普通节点上的 context.assembler。修改文本正文后，每次装配读取当前文本；预览不会消费事件。
