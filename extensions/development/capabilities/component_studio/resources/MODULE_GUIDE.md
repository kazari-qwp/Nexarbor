# 模块契约 nexarbor-module/v1

组件清单 module.json 指定 id、version、固定入口 module.py:Module、node_types、requires、config_schema、state_schema、tools 和 signals。requires 是已发布模块的ID，按依赖顺序加载；不会自动给节点挂载依赖，也不会执行包安装器。example.json 必须包含可运行的 config。

```python
from datanet.studio.contract import StudioModule

class Module(StudioModule):
    def setup(self):
        self.state.setdefault('count', 0)

    def count(self):
        return dict(count=self.state['count'])

    def on_signal(self, context):
        self.state['count'] += 1
        return dict(count=self.state['count'])
```

tools 的每项为 {name,description,parameters,channels}。channels 可直接提供字符串列表，也可使用 {"config":"某个配置字段"}；空列表只允许本地访问。parameters 使用 object JSON Schema。没有 read_only 或 visibility。工具方法接收声明的关键字参数，返回可JSON序列化的值或NodeResult。工具由宿主装配，远端每次调用仍检查显式开放、频道和强度。

signals 是模块愿意响应的频道列表，任意重叠时才调用 on_signal；不匹配时不执行这个模块，核心仍继续传播。异步回调会等待完成。同一节点挂载多个模块时依次响应，整层节点由核心并行。状态应能JSON序列化并满足state_schema。文本节点可以调用本地 node.write('content', text)，这不是网络权限入口。

context.signal.signal_id 是核心提供的唯一信号身份；不要用 content 代替身份，同一份消息内容也可能发出多次。需要幂等时记录 signal_id。使用相对导入（例如 from .helpers import ...）复用模块目录内的其他Python文件。宿主不修改用户系统Python，也不安装模块提出的依赖。

tests/test_*.py 使用 unittest 编写业务测试。工作室另外持有固定契约检查，不能通过改测试绕开。执行测试会运行Python代码，普通子进程不等于安全沙箱；工作目录独立，固定检查有时间上限。源码变化后必须重新验证，验证通过的确切内容才能发布；发布版本不可原地改写。修改已挂载模块要先卸载，当前信号执行结束才能更换实例。

## 组件之间协作

可选operations清单为[{"name":"操作方法名","parameters":{"type":"object",...}}]，对应同名实例方法。这些操作只供可信组件调用，不会自动变成Agent工具。backend.modules.call(node_id,module_id,operation,arguments)验证操作参数和结果状态；backend.modules.get可读取指定已装配实例。依赖模块ID写在requires中，宿主按依赖加载；实例的节点ID和组件引用一律作为配置传入。setup只初始化自己的缺失状态，不主动调用尚未完成装配的依赖。

工具内可信调用者：from datanet.core.access_budget import current_agent_id；current_agent_id()取得发起Agent节点ID。不要把调用者身份作为模型可填写参数。工具调用的可达性与频道由核心检查，但业务前提与行动消耗由组件自行检查。tool_description(name,default)可根据实例config生成工具描述；不要修改共享清单。

常用核心对象：backend.network.nodes是ID到Node的字典；Node.connect(target,channels=[...],threshold=1,multiplier=1)建立有向连接；node.interfaces列表中的edge有target_node_id和metadata.channels。backend.modules.mount(node_id,module_id,config,state,bind=False)装配实例；新建节点后调用backend.modules.refresh()重建通用信号绑定（不会执行任何业务）。不得通过无关频道授予移动/工具/信号权限。

持久状态写self.state（JSON对象），配置写self.config。self.node.inputs.update(source,{system_prompt:文本,context:[{id:文本,text:文本}],inputs:[{id:唯一ID,text:文本}],tail:[文本]})设置Agent四路输入，四个字段都可只更新一部分。memory_read/memory_write是核心Agent节点自己的私有工具。backend.dispatch('save',{'full':True})请求全量存档。

Node/AgentNode/TextFileNode/PulseNode分别从datanet.core.node/agent_node/text_node/pulse_node导入。普通节点构造Node(id,name,None)；AgentNode(id,name,file_path=backend.directory/'相对记忆路径.md')；文本节点TextFileNode(id,name,'text',backend.directory/'相对路径.md')。新节点用backend.network.add_node(node)注册。模块卸载时应移除自己注册的元数据provider等监听。

原生Agent执行端口：await backend.execute_agent(node_id,message='')，可在async on_signal中等待其正常结束。节点execution配置为{"executor":"harness","strength":2,"max_steps":12,"timeout_seconds":90,"prepare":[{"module":"某模块ID","operation":"某个同步操作","arguments":{}}]}。prepare操作会在每次模型请求前调用（默认本节点，也可reference.node指定），适合刷新四路输入。宿主自动装配核心私有记忆工具与当前强度可达的公开工具，动态检查权限，不需组件手工注册模型工具或实现模型循环。节点inputs里放人格、常识、地图和现场资料，宿主按四路原生通道更新。

多个实体状态需要一起变更时，可以使用 with backend.modules.transaction(节点ID1,节点ID2,...):，异常时会恢复这些节点所有模块的原有state；省略节点ID表示全部模块。该事务只保护模块状态，不能回滚文件、外部I/O、新建节点或接口操作。只包住短暂的同步修改，不能跨await等待模型。先验证业务前提，再扣行动值及转移资源。

tool_enabled(name)默认True。组件可以按实例config覆盖它，只装配该实例真正提供的工具；不适用的工具返回False，不要暴露一堆只能拒绝的工具。tool_description(name,default)同样可以按配置返回简洁、具体的说明。

on_tool_denied(name,actor,reason)可返回面向调用者的简短拒绝说明，默认原样返回reason；这个回调只解释，不得扣费、发送消息或做任何业务修改。原生宿主在曾经可见的工具后来不可达时可以调用它；不会因此执行原工具或重新授予权限。

依赖接线完整后的应用测试由装配者另行运行。组件自己的tests必须覆盖主要成功、失败、状态恢复与重复调用场景；不要修改宿主验收，不需要为不存在的旧接口写兼容层。README必须列明config、operations、tools、signals和返回结果，装配者只看文档和配置就能接线。
