# 用 Module 完成局部行为

入口是 Module 子类，公开操作是普通方法，直接返回业务值：
```python
from domain.core import Module, access

class Counter(Module):
    def __init__(self, config=None, state=None, **settings):
        super().__init__('counter', **settings)
        self.config = config or {}
        self.state = state or {}

    def increment(self, amount=1):
        return next(iter(self._increment(amount).values()))

    @access(channels=())
    def _increment(self, node, amount):
        self.state['count'] = self.state.get('count', 0) + amount
        return {'count': self.state['count']}
```
清单格式 nexarbor-module/v4，entry 是 module.py:Counter。声明 id、中文 name、version、node_types、requires、config_schema、state_schema、operations、signals。operation 有 name/channels/parameters/result，parameters 校验传入方法的关键字参数，result 校验返回值。不再返回 ComponentResult。

项目组件由 module.json 加载自己的 Python 类和辅助文件；框架安装层的注册材料不能当作项目模块入口。按需声明 transaction、emit、agent_run、checkpoint、instantiate、directory 构造参数，由宿主注入相应运行端口；不接收 Backend 或整个网络。外部工具仍按14的实际工具接口调用。

node_types 必须包含真实装配对象：NPC 是 agent，场所一般是 node，Markdown 数据是 markdown。AgentNode 继承普通节点；MarkdownAgentNode 复用 Markdown 数据和记忆，普通节点没有 dataer。测试用 add_node('npc',agent=True)，判断真实类型用 node.node_type，不猜 has_agent 或 data_kind。

config 是装配规则，state 是本实例持久状态。初始值、价格放 config，运行结果放 state。它们是 JSON 数据，不再通过旧冻结配置接口访问；不以全局字典保存其他节点状态。跨实例操作须在 access 回调内通过实际模块公开方法完成。

JSON Schema 的 default 只是说明，不会自动填入 config/state。装配可从发布的 example.json 开始；测试也要填写实际使用的默认配置。signals:{config:'signal_channels'} 从实例 config 读取接收频道，省略就是没有接收频道。

access 回调中的 node 是实际到达的节点：node.info 提供身份、名称和说明，node.modules / node.tools / node.links 是本地表。自身模块的稳定身份是 self.module_id，发布资料用 self.published。Agent 的 update_inputs(source,**patch) 更新 system_prompt/context/inputs/tail；人格用 system_prompt，当前地点用 tail，一次性事件用稳定 id/text 的 inputs。

Markdown 正文用 node.dataer.read()、node.dataer.write(text)，直接读写真实文件；修改片段和追加也在 MarkdownDataer。普通 Node 没有文本能力，读取前应使用明确的数据节点类型，不能猜 content 或 __text__ 键。其他数据节点按其 Dataer 接口处理。

反例：execute(backend,node,amount)、通过 Backend 查全网、读取会话日志。正确：模块通过 access 获取节点；跨节点方式见02。
