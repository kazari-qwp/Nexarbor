# Agent四类输入与上下文装配

核心定义输入契约，独立装配器组织来源，执行器适配层送入原生通道。工具注册、工具权限、工具结果和执行状态不归入这四类。没有用四类正文重新拼接整个Harness请求。

## 当前 v3 模块工作流

新网络使用普通模块 `context.assembler`，推荐装在角色的亚节点上，以独立出边读取四类文本。默认频道为 `context.assembler.system_prompt` / `.context` / `.inputs` / `.tail`，串联频道为 `context.assembler`；均可配置频道列表和黑白名单。同时支持直接文本和项目文本路径。Agent 的 `execution.prepare` 显式引用组装器，同归属树通过核心本地调用，外部仍检查可达性。见 [亚节点](SUBNODES.md)、[上下文组装案例](CONTEXT_ASSEMBLER_CASE_STUDY.md) 和组件 README。

下文 Application 插件接口保留给旧运行环境；新制作 Agent 应使用上述 v3 模块，不再使用应用级 `agents.context`。

## 核心输入接口

```python
# 纯核心：只更新节点数据，由使用它的执行器消费。
node.update_inputs('producer', system_prompt='固定职责', tail=['第1天-早'])

# 已绑定的Application：更新、持久化并交付原生执行器。
app.update_inputs(actor, 'producer',
    system_prompt={'file': 'E:/example/personality.md'},
    context=[{'id':'guide','text':{'file':'E:/example/guide.md'}}],
    inputs=[{'id':'event-001','text':{'file':'E:/example/task.md'},'delivery':'followup'}],
    tail=[{'file':'E:/example/status.md'}])
```

四口均接受文本或`{"file":"绝对路径"}`，文件按UTF-8文本读取，不执行内容。核心接口接受可信宿主提供的路径；没有新增Agent可调用的任意文件读取或输入更新工具。直接文件输入在更新时读取并保存正文快照；需要反映文件改动时再次更新，装配器文件来源则每次装配读取最新正文。

- `system_prompt`：当前来源的系统提示快照；各来源独立section，按稳定来源顺序装配。省略不变，空字符串清空。Harness自行比较最终系统文本，不维护第二套系统提示已加载缓存。
- `context`：当前来源的文档清单，每份有稳定id/text；清单空列表撤下当前来源。原生文档通道检查正文摘要及当前历史/待入队标记，首次、正文变化或压缩丢失才入历史。清空清单不会抹去已产生的历史。
- `inputs`：新事件清单，默认followup，可设steer；按来源+事件ID去重。省略或空列表均不新增事件，不代表撤回已入队任务。同一ID内容变更明确拒绝；相同正文的不同事件ID仍分别投递。保存pending/delivered状态，原生适配层检查稳定消息ID、接收集合和原生队列日志，覆盖消息已接收但尚未入历史的窗口；原生队列日志flush后才确认交付。
- `tail`：当前来源的尾部文本清单，每请求使用最新快照，不进入对话历史；空列表清空。

省略字段不影响其他字段，不覆盖其他来源的内容。当前来源、文档正文和事件回执随Agent节点网络/Backend检查点持久化。纯核心恢复测试覆盖未投递及已投递状态。参考MinimalExecutor也消费同一快照，尾部不写入历史。

## 可选共享装配器

组件：`capabilities/context_assembly`。取代旧`prompt_matching`，不保留旧入口。无信号、NPC或元数据扩展器依赖，直接使用统一Network.get_metadata；没有扩展器时照常匹配核心字段。agent_runtime和network_access依赖它，使这些运行环境中每个已绑定Agent默认参与装配。没有绑定来源时不注入内容、不启动模型。

装配节点使用普通核心Node，不新增专用核心类型。宿主配置并绑定：

```python
assembler=app.plugins['capabilities/context_assembly']
assembler.configure('context-node', [
    {'id':'personality','kind':'system_prompt','source':{'type':'file','path':'E:/example/personality.md'}},
    {'id':'profession','kind':'context','when':{'/extensions/npc/role':'miner'},
     'source':{'type':'resource','component':'nodes/resident_knowledge','file':'profession/miner.md'}},
    {'id':'time','kind':'tail','source':{'type':'node','target':'clock'}}
], document_roots=['E:/example'])
assembler.bind(actor,'context-node')
assembler.assemble(actor)
```

配置来源支持text/node/file/resource，投放类别为system_prompt/context/inputs/tail；when支持核心字段名或JSON Pointer、列表表示候选值，order后按id稳定排序。事件来源必须有event_id，不能把同一事件ID当动态文本反复修改。state: ID前缀保留。reference_only只用于context节点来源，提供按需读取入口。

绑定本身不授予读取权限：Agent必须有指向装配节点的直接读取连接；装配节点必须有指向节点来源的直接读取连接。各自按Agent预算验证门槛与私有权限，不扫描业务邻居，不自动递归子节点。文件来源要求宿主显式授予document_roots，组件资源要求组件已启用且路径位于其资源目录；文件重定向到根外会拒绝。固定文档无需创建节点。

装配器按匹配条件生成四份更新，通过同一核心接口交付。条件文档自带条件；元数据/适用的系统与文档来源变化才生成新修订记录，A→B→A重新通知。时钟等尾部变化不产生新历史状态记录。文档是否已加载以原生历史为准。撤销读取连接或停用组件会清空其当前系统/文档清单/尾部，不声称删除旧历史或撤回已入队消息。

## NPC接线

```text
脉冲 → 时间文本 → NPC → 脉冲             信号链
NPC → 自己的装配节点 → 时间文本           私有读取关系
                     → 匹配的知识节点
                     → 固定人格文件       清单中的组件资源
```

每名初始NPC有独立人格Markdown，儿童用独立人格模板，均无NPC写入权限；人格走系统section，职业知识走历史文档，家庭知识只给入口。NPC不再直接连接时间，时间是普通文本，短状态由世界模块通过tail口提供。世界每时刻任务通过inputs口入原生队列，仍使用原生Agent循环自然完成。

旧文本模块的隐式常驻文本尾部扫描、resident_texts、write_resident_text及resident投放模式已移除；按需query_text和标准node_read/node_write仍保留。不迁移前两个应用的旧常驻文本预设，本轮只保证新核心、通用装配组件和NPC链路。

## 原生适配

系统sections → Harness系统提示投影；context → InstructionHistory；inputs → followup/steer与原生Inbox；tail → agent/request-tail。保留Harness自有提示、Skill及工具装配；本模块只管理自己的来源。接口为宿主API，不增加NPC可见工具。
