# 模块契约 nexarbor-module/v2

你在制作一个局部组件。构造器只接收 ModuleContext，基类提供 self.context、self.config、self.state。没有 self.backend、self.node、全图扫描、宿主目录、任意 RPC 或其他实例引用。不要编写旧接口兼容层。

module.json 声明 format=nexarbor-module/v2、id、version、entry=module.py:Module、node_types、requires、config_schema、state_schema、tools、signals，以及可选 operations。requires 仅表示组件代码依赖，不自动装配或授予网络访问。example.json 提供 config，可选 access 仅供验证示例；实际授权由装配者决定。

```python
from datanet.studio.contract import StudioModule

class Module(StudioModule):
    def setup(self):
        self.state.setdefault('count', 0)

    def on_signal(self, context):
        self.state['count'] += 1
        self.context.publish_metadata({'count': self.state['count']})
        return {'count': self.state['count']}
```

tools 每项为 {name,description,parameters,channels}，对应同名方法。channels 是列表，也可为 {"config":"字段名"}。operations 每项为 {name,parameters,channels}，也对应同名方法；它们不会自动成为 Agent 工具。空频道接口只允许本节点调用。参数 Schema 必须为 object。异步方法正常使用 async/await，结果只能是 JSON 数据或 NodeResult；不能返回实例、函数、文件句柄或原始状态引用。

网络 API：

- self.context.network.nodes(channels=None,strength=None)：授权范围内的元数据、path、剩余 strength。
- self.context.network.metadata(target,...) / tools(target,...)：可达节点元数据和公开工具定义副本。
- await self.context.network.call(target,module_id,operation,arguments)：调用可达组件的公开操作。
- await self.context.network.invoke(target,tool,arguments)：调用可达公开工具。
- await self.context.network.emit(channels=...,strength=...,content=...)：从本节点发送信号，返回源端回执。
- 不允许改起点、扩大授权频道或强度。转调继承当前剩余范围；不能用另一条无关频道的路径绕过接口频道。
- 节点 ID 只是引用，不是权限。获取一个 ID 不代表可以访问它。没有“读写”“公私”旧分类。

本地 API：

- self.context.metadata()：所在节点元数据副本。
- self.context.publish_metadata(fields)：仅发布本节点、本模块命名空间，卸载自动撤销；由 setup 从 self.state 重建。
- self.context.read(request) / write(key,value,mode='upsert')：本节点自身提供的数据能力。
- self.context.update_inputs(patch)：本 Agent 的四路输入，固定来源 module:模块ID；字段为 system_prompt、context、inputs、tail。只接受文本，不能通过 file 字段加载任意磁盘路径。
- self.context.caller_id：框架绑定的最初调用者身份，不要让模型填调用者参数。
- config 不可变，state 只属于当前实例。跨实例变更必须通过公开操作；不要读别人内部字段或修改核心。

signals 是响应频道列表。频道任意重叠时执行 on_signal(context)，不匹配仍可继续传播。context 只有不可变 signal 和 delivery，没有 network。signal.signal_id 用于幂等；相同 content 不代表同一次信号。接收信号不会获得发送者或信号所携带频道的权限，响应按本实例装配授权执行。整层完成后才继续下一层。

回调完成就失去这次接口授权；不要创建脱离回调生命周期的后台业务。卸载、禁用和同位置重装后旧上下文、旧工具和旧异步调用均失效。组件的 setup 只初始化自己的状态，不要求尚未完成 install 的依赖已经提供操作。

如果确实需要入边扫描或网络编辑，在 README 说明需要装配官方网关 network.gateway、哪些 operations/targets，以及通过哪个频道访问。普通模块不能自授 extension，也不能请求原始 Backend 或任意宿主执行能力。保存全局网络、运行模型、访问外部系统等未由本契约公开的能力，先向装配者说明缺少的官方服务，不要用 import/文件读取绕过接口。

tests/test_*.py 使用 unittest，覆盖成功、拒绝、恢复和幂等场景。测试可以构造 Network、NodeModules 和假宿主作为夹具，生产组件不得借此获得全局对象。验证由宿主运行，不修改宿主验收。只修改工作副本，不读取工作目录外源码或凭据，不联网、不安装依赖、不调用终端。新增依赖先说明需求。

README 列出 config、state、operations、tools、signals、所需装配授权和返回值。所有实例差异通过配置表达，不写死某个应用的节点 ID。框架接口隔离不是恶意 Python 沙箱，不能宣称已实现操作系统级隔离。
