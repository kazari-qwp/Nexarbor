# 用四路输入装配上下文

先复用 context.assembler / context.text。推荐给角色挂一个亚节点，在里面装普通组装器；亚节点有独立出边，父节点通过 execution.prepare 本地调用，不需要额外业务边。亚节点也能嵌套；模块表、工具表不合并。若需要父对象的边，用核心开关，不在模块里维护私有表。

默认文本频道为 context.assembler.system_prompt / .context / .inputs / .tail，串联频道为 context.assembler；都可配置列表和黑白名单，前端用条目与加号。串联会合并稳定来源、去重并停止环路。短文本直接填 sources，文件用项目相对 path，不必为每份文本制作新模块。

system_prompt 是系统快照；context 是正文变化才更新的资料；inputs 用 event_id 去重；tail 是每次请求重读的快照。条件用 when + 显式只读 bindings，本地父对象引用可填 $parent；详情按需读组件 README / module.json。

正确示范：clock.counter 打开 write_text，用 text_template 定义文本；时钟文本装 context.text，亚节点按 tail 频道读取。用户能看连线、改模板、读正文和预览来源。

反例：角色模块硬编码时钟 ID，悄悄 update_inputs；把人格、记忆、地图、活动都塞进 prepare；执行器无条件添加应用提示。这使配置不能替换，跨应用复用失败。

先预览，再运行。验证重路去重、串联环路、错频道隔离、文件权限、条件变化、事件不重放。纯读取不需要隐藏中间态，不要加节点事务锁。
