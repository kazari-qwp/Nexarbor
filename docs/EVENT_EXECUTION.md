# 事件触发器与模块执行器

权限网络决定谁能访问谁，执行图决定节点响应事件时先后执行什么。两者独立；业务模块不需要认识后继模块。

## 组件依赖

- `capabilities/langgraph_backend`：包装官方 langgraph 1.2.16 的 StateGraph/ainvoke。
- `capabilities/module_execution`：依赖后端，执行宿主授予的模块操作。
- `capabilities/event_trigger`：依赖后端和执行器，匹配事件并选择图。

后端位于可选组件中，核心没有 LangGraph 导入。原来的 signal_response 已删除，没有旧接口适配。clock.text、agent.signal、checkpoint.counter 直接使用新接口；NPC 预设现有的准备步骤转换成结构化图，原有权限、行动规则和提示词保持现有语义。

```powershell
python -m pip install -r extensions/foundation/capabilities/langgraph_backend/requirements.txt
```

## 结构化执行图

call 具有唯一 id、operation、arguments；operation 是宿主授予的名称。sequence 顺序执行 steps；parallel 同时执行 steps，全部完成后返回；branch 的 select 使用 JSON Pointer，标量转字符串后匹配 cases，未匹配执行 default。所有子块可嵌套。

```json
{
  "type": "sequence",
  "steps": [
    {"type":"call","id":"check","operation":"check","arguments":{}},
    {
      "type":"branch",
      "select":{"$ref":"/results/check/value/status"},
      "cases":{
        "moved":{
          "type":"parallel",
          "steps":[
            {"type":"call","id":"old","operation":"refresh_old","arguments":{}},
            {"type":"call","id":"new","operation":"refresh_new","arguments":{}}
          ]
        }
      },
      "default":{"type":"sequence","steps":[]}
    },
    {"type":"call","id":"publish","operation":"publish","arguments":{}}
  ]
}
```

图只支持有界结构化组合，不开放任意循环或代码执行。最多 256 个块、16 层嵌套；call id 在整图唯一。需要循环时交给独立脉冲节点，而不是在配置里创建无限边。引用只能读取输入 event 和已完成的 results；不能依赖并行兄弟尚未完成的结果。引用缺失会明确报错。

每个结构化组编译成 LangGraph 子图。条件分支作为完整子图参与外层并行屏障，因此不等待未启动的分支；外层后继也不会因为短分支提前完成而提前执行。并行结果按唯一 id 合并，不承诺完成顺序。

## 事件规则与程序接口

事件是 JSON 对象：`{type, channels, payload}`。规则是 `{id,event,channels,where,graph}`。event 精确匹配 type；channels 非空时要求有交集，空表示不限制；where 的每个键是指向事件封套的 JSON Pointer，值是要求相等的 JSON 值。不存在的字段不匹配。多个命中规则按配置顺序执行。

```python
trigger = app.plugins['capabilities/event_trigger']
graph = {'type':'call','id':'refresh','operation':'refresh','arguments':{}}
rules = [{'id':'arrival','event':'place/arrived','channels':['scene'],
          'where':{},'graph':'refresh'}]
trigger.bind(node_id, rules, {'refresh':graph}, {'refresh':refresh}, binding='scene')
report = await trigger.emit(node_id, {
    'type':'place/arrived','channels':['scene'],'payload':{'actor':'npc'}
})
```

操作签名 `(context, **arguments)`，可同步或异步。同步操作在线程执行；返回可等待对象也会等待。context 对信号是原有 SignalContext；普通事件可显式传入，默认 None。参数通过 `/event/payload/...`、`/results/步骤ID/value/...` 引用，不能 eval 或插入函数路径。框架 NodeResult 错误会中止图并上报。

直接运行执行器：`await app.plugins['capabilities/module_execution'].execute(node_id, graph, operations, event, context)`。也可以显式装配 `modules.executor` 后调用其同名 execute 方法；operations 是宿主提供的 Python 可调用表，不是事件输入。

响应报告为 `{matched, executions:[{id,graph,results:{步骤ID:{operation,value}}}]}`。无匹配规则时 matched 为 0，不妨碍信号中继。

## 节点装配

把以下配置作为节点模块 event.trigger 的 config，state 使用空对象。它引用同节点已有的模块：

```json
{
  "operations": {
    "info":{"module":"information.collector","method":"collect"},
    "tools":{"module":"tools.assembly","method":"assemble"},
    "context":{"module":"agent.signal","method":"assemble"}
  },
  "rules":[{
    "id":"arrived","event":"node/tool-invoked","channels":[],
    "where":{"/payload/actor":"world/npc/miner","/payload/tool":"move_here"},
    "graph":"refresh"
  }],
  "graphs": {"refresh":{
    "type":"sequence",
    "steps":[
      {"type":"parallel","steps":[
        {"type":"call","id":"info","operation":"info","arguments":{}},
        {"type":"call","id":"tools","operation":"tools","arguments":{}}
      ]},
      {"type":"call","id":"context","operation":"context","arguments":{}}
    ]
  }}
}
```

这个配方已在临时小镇测试，未作为默认移动机制写入预设。它复用现有收集器和工具装配器；“场所共用动态文本替换收集器”和此前讨论的行动值调整属于后续应用配置工作。

应用普通事件使用 `app.emit(name, **payload)`；异步调用方使用 `await app.emit_async(name, **payload)`。监听器接收封套 type=name、channels=payload.get('channels',[])、payload=原始参数。同步 emit 若遇到异步监听器明确报错，避免把未等待任务当作完成。

独立宿主在网络和 Application 就绪后调用 `backend.modules.bind(app)`，才能接通节点模块；disk_network 已在其根会话入口执行这一步。重复绑定不会重复注册事件监听器。不要在核心事务锁内发送需要执行线程/Agent 的事件。业务成功事件应在事务提交后发布；执行图失败不会回滚先前已经完成的外部副作用。

## 信号、权限与恢复

信号被包装为 type=signal/received、channels=原信号频道、payload={signal,delivery}。核心仍使用原有逐层并行屏障；整个节点图结束后才进入下一层。节点处理期限和失败策略仍由 SignalRuntime 执行，失败不会冒充完成。

同节点可以有多个命名 binding。信号绑定必须具有相同的接收者权限强度；卸载一个绑定不影响其余绑定。每次操作执行前重新检查绑定及模块是否仍存在/启用。事件只能携带数据，不能创建新授权。

执行器拒绝同节点重入。同步线程超时/取消后无法强杀，因此跟踪全部尚未结束的线程，直到全部退出才允许重入。调用方需要为可能阻塞的操作设置自身期限；信号路径已经提供节点和整信号期限。普通事件的同步等待入口只用于有界操作；异步入口可以由调用方使用 asyncio.wait_for 限时。同节点递归触发自身执行图会拒绝重入，应改为同一图内的后续步骤。

模块配置、领域状态和事件绑定配置随核心提交保存；Python 函数、LangGraph 调用期状态不写入快照。恢复后由节点模块/宿主重绑操作，不重放中断的步骤。纯程序方式注册的普通事件还需要宿主重新发布或安装监听器，保存配置不等于保存函数或自动订阅。

## 官方后端

[官方安装](https://docs.langchain.com/oss/python/langgraph/install)；[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)。使用本地 Python 包即可，不依赖云端图服务，也不新增模型 API 调用。
