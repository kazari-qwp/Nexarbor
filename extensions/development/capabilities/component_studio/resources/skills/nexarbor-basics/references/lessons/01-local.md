# 用 ctx 完成局部行为

入口固定，返回固定封套：
```python
from datanet.core.module_protocol import ComponentResult
async def execute(ctx, activation):
    if activation.kind == 'access' and activation.operation == 'increment':
        ctx.state['count'] = ctx.state.get('count', 0) + activation.parameters.get('amount', 1)
        return ComponentResult(data={'count': ctx.state['count']})
    return ComponentResult(status='error', error='不支持的请求')
```
清单格式 nexarbor-module/v3，entry 是 module.py:execute。声明 id、中文 name、version、node_types、requires、config_schema、state_schema、operations、signals。每项 operation 有 name/channels/parameters/result，parameters 是对象 Schema，result 校验返回 data。

项目组件由 module.json 加载 module.py；样板中某些 component.json / python/services.py 是框架安装层的注册材料，复制进项目模块不会执行，也不能据此给自己新增宿主能力。可用宿主端口用 catalog_ports 查询。

node_types 必须包含真实装配对象：NPC是 agent，场所一般是 node。可复用记录仓要支持两者。测试用 add_node('npc',agent=True) 创建真实 Agent，不能把它换成普通 node，再放松身份检查来迎合错误声明。metadata()['node_type'] 是准确的核心类型；需要 Agent 身份就严格等于 agent，不猜 has_agent 或 data_kind，不在查询失败时放行。

config 是只读装配规则，state 是本实例持久状态。初始值、价格等放 config，运行结果放 state。不用全局字典保存所有节点数据，不绕过 ctx 操作其他实例。沿频道取得节点对象后，可以读取其模块的 config/state 副本；修改副本不会提交状态，跨实例业务修改通过公开操作完成，接口见02。

JSON Schema 的 default 只是说明，不会自动填入 config/state。正常装配可从发布的 example.json 开始；测试也要显式填写实际使用的默认配置。尤其 signals:{config:'signal_channels'} 从实例 config 读取接收频道，省略字段就是没有接收频道。

ctx.node_id/module_id 是本实例身份；metadata() 读本地资料，publish_metadata({...}) 在本模块命名空间发布。update_inputs({...}) 更新本地 Agent 的 system_prompt/context/inputs/tail：人格用 system_prompt，当前地点用 tail，一次性事件用有唯一 id/text 的 inputs。

config、parameters、signal.content 是冻结 JSON：对象 FrozenDict，数组 tuple。可变副本用 datanet.core.json_values.thaw，不修改 config，不把数组只当 list。

文本节点的本地正文键固定为 content：`ctx.read({'method':'key','key':'content'})` 返回 NodeResult 的 JSON 副本（status/items/sources/errors）；`ctx.write('content','新正文')` 写入，同样检查 status 是否为 ok。不是 __text__，也不能猜其他键。普通 node/agent 并不自动具有文本写入能力；文本写入要声明 text_file。

反例：execute(backend,node,amount)、backend.network.nodes 查别人、open 会话日志。正确：只经 ctx，需要其他节点时读 02。
