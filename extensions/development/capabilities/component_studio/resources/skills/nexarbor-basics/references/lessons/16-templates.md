# 固定模板与独立实例

需要在运行中重复创建一组节点时，宿主提供 `templates:instantiate`。模板是声明数据，不是启动脚本。网络制作在工作副本 `runtime.json` 写 `{"templates":[...]}`；`copy_current_network` 会复制当前登记的模板。`validate` 检查声明，自测加载同一配置，发布时写入现有完整网络的运行时元数据。带模板的成品按完整网络打开，不当作可以任意拼接的片段拖入。

每个模板的字段必须齐全：

| 字段 | 含义 |
|---|---|
| `id` | 1–80 字符，字母、数字、下划线、点、连字符 |
| `callers` | 可发起实例化的现有节点 ID 非空列表 |
| `document` | 普通 `{network,files}`，包含 1–16 个模板内部节点；无运行信号和委托 |
| `arguments_schema` | 本次参数的 object JSON Schema |
| `bindings` | `[{"path":"/network/nodes/0/name","input":"label"}]`；从参数 `label` 或 `/list/0` 取值。可改名称、说明和模块 config，不能替换执行身份或任意代码 |
| `attachments` | `[{"source":"现有节点ID","target":"模板内部ID","metadata":{...}}]`；实例化后补入现有节点到新节点的连接 |

节点用 `node_template` 取得当前核心骨架，填普通模块、配置、状态、权限与接口；模板内也能有亚节点。对外连接引用已存在的节点。模板自身的记忆／文本文件必须有独立的 `document.files` 初始正文，不带旧会话、输入确认或活动状态。

内部 ID 实例化时会重新分配。父子归属、连接、执行准备引用，以及模块 Schema 中 `format:"node-id"` 的字段会重映射；普通字符串不会被猜测为节点引用。模块的所有数据和出边规则仍由现有核心处理。文本、工具、执行准备和后续信号需要怎样的可达路径，都应在模板与 attachments 中真实表达。

模块调用仍通过 offer、频道与可达路径：

```python
result = await ctx.network.invoke(ctx.node_id, 'templates:instantiate', {
    'template': 'unit-template', 'key': stable_request_key,
    'arguments': {'label': '新实例'},
}, channels=['runtime.template'])
```

提供节点需有 `offered_tools:[{"ref":"templates:instantiate","channels":["runtime.template"]}]`。创建在业务事务提交后执行；同 key、同参数重试返回同一组 `node_ids` 和 `duplicate:true`，变参会失败。配合局部待办与回执恢复，不能在长事务里创建再等待模型。模板声明不表示业务已经通过。

在 `NetworkHarness` 中使用相同端口：

```python
created = await h.invoke('factory', 'factory', 'templates:instantiate', {
    'template': 'unit-template', 'key': 'case-1',
    'arguments': {'label': '新实例'},
}, channels=['runtime.template'])
```

检查真实新节点的独立数据、亚节点归属、上下文输入包的消费、工具检索与下一轮信号；重开存档后同 key 不得再创建一套。模块作者可在当前网络的隔离副本验证已有模板；新增配置要交给网络制作一同装配，不能只在测试里补配置、发布成品却遗漏。局部网络管理员不替换整个项目的宿主模板。
