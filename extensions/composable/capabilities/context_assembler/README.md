# 上下文组装器

普通节点上的通用 v3 模块。角色只有一条 context.assemble 出边到组装节点。组装节点再用 system_prompt / context / inputs / tail 四种频道分别连接装有 context.text 的文本节点，可以经过同频道的普通中继节点。每类频道单独遍历，同一来源同类只读取一次；聊天、移动、业务频道不会混入。

在角色的 Agent 执行设置里添加：
```json
{"executor":"harness","strength":2,"channels":["context.assemble"],"prepare":[{"node":"组装节点编号","module":"context.assembler","operation":"assemble","arguments":{},"channels":["context.assemble"]}]}
```
这里的强度必须足以到达相邻组装节点。组装器读取下游的范围由它自己的模块强度和频道决定。prepare 的跨节点调用同样受可达性检查；不是全局后门。组装器不写别人的输入，只返回 nexarbor-context/v1 数据包，由执行适配器交付四路接口。删除准备引用后，旧快照撤下，已经排队的事件仍保留。

## 三种来源

- 文本节点：给节点装 context.text，正文在工作台正常编辑。类型在连线上；同一文本也可以显式投放到不同类型。context.text 可配置 order、when、event_id、delivery、enabled。
- 直接文本：sources 每项填写稳定 id、kind、type:text、text。
- 文本路径：sources 每项填写稳定 id、kind、type:file、path。相对路径从当前项目文件夹解析，每次装配重读 UTF-8 文本；项目 context/ 目录参与 Commit。默认不能越出项目，document_roots 是显式授予的额外目录。缺失、非 UTF-8、越界、超过 1 MiB 都有来源错误。

文件读取需要 example.json 中的 read_text 扩展授权，仅官方原样组件拥有这个只读端口。普通制作模块仍不得 open 任意文件。组装器没有任何 NPC、钟表、地图或私人记忆知识。

## 条件与顺序

when 是字段等值条件，字段可以是 JSON Pointer。默认匹配本组装节点元数据；需要业务事实时，bindings 显式填写目标节点、模块、只读操作、参数、频道和结果 JSON Pointer，读取对象字段用于匹配。例如 records.store.read 的 /values。必须有实际连线和授权，不会猜角色 ID 或扫描业务网络。多个来源按 order、稳定 id、kind 排序；context 文档 ID 稳定。

inputs 必须填写独立稳定 event_id；相同事件只投递一次，同 ID 改正文会明确报错，新的事件使用新 ID。system_prompt 是当前系统快照，context 是按正文变化更新的资料，tail 是每次请求重读的快照。预览不会投递事件，不会更改 Agent 输入或模块状态。

## 工作台

模块页面可添加直接文本或文件、选择类型、保存配置，点击“装配预览”查看四路成品、原节点/文件完整路径、实际频道、路径、匹配结果和错误。来源配置可预览草稿，连线使用已校验更新的运行网络。高级条件和授权通过通用表单编辑。

与私人记忆、地点查询分开使用。教材见 docs/CONTEXT_ASSEMBLER_CASE_STUDY.md。真实运行时测试：tests/test_context_assembler_v3.py。
