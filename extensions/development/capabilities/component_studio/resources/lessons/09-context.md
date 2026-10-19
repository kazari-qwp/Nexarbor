# 用四路输入装配上下文

先复用 context.assembler / context.text。角色只通过 context.assemble 连到相邻普通组装节点，文本从组装节点按 system_prompt / context / inputs / tail 四频道分别展开。短文本直接填 sources；文件用 type:file + 项目相对 path；不必为每份文本做新模块。

system_prompt 是当前系统快照；context 是正文变化才更新的长效资料；inputs 是 event_id 去重的一次性事件；tail 是每次请求读取的当前快照。需要动态条件用 when 和显式只读 bindings，详情按需读组件 README / module.json，不猜字段。

角色 execution.prepare 显式引用组装节点的 assemble，并限定 channels:["context.assemble"]；执行器 channels 也包含它。跨节点 prepare 同样检查可达性。组装器独立设置四种读取频道和模块强度。

正确示范：将 clock.counter 的 write_text 打开，用 text_template 定义输出；时钟文本节点装 context.text，从组装节点用 tail 接它。用户能在工作台改模板、读正文、预览来源。

反面示范：在角色模块里读取硬编码时钟 ID，再悄悄 ctx.update_inputs(tail=...)；一个模块同时管人格、记忆、地图、活动；执行器无条件加应用提示词。这让接线不可见、配置不可替换，跨应用复用失败。

先预览再运行。检查四路成品、来源路径、匹配结果；预览不消费 inputs。测试重复路径只读一次、业务频道不能扩散、事件不重放、文件权限、条件变化。读取没有需要隐藏的中间态，不要给装配加节点事务锁。
