# 需要用户讨论的兼容点

## B001：锁事务的拓扑隔离与新 access 的读取入口

状态：待讨论；尚未修改新核心，也未写代理/快照替身绕过。

旧行为证据：

- `E:/DataNet-模块化成品/tests/test_node_locks.py:224` 的 `test_uncommitted_topology_is_not_visible_to_other_owners`。
- `python/datanet/core/network.py:34` 的 routing_snapshot 调用锁服务的 routing；walk_states 第 111 行使用快照。
- `python/datanet/core/node_locks.py:482` 的 routing 为其他事务提供已提交连接视图。

旧契约：事务持有 A/B 并临时移除 A 的出边时，其他访问者不能看到尚未提交的连接变化；失败或取消还要完整回滚。

新实现现状：`domain/access.py:44` 直接遍历当前 `node.links`，汇合及偏置也直接读目标对象；没有事务读取快照或访问生命周期接入点。

不能直接把旧锁类复制进来就宣称隔离已实现。全局串行执行、临时替换私有字段、代理旧 Node、把新装饰器闲置而走另一套图遍历，都不能作为未经同意的解决方案。

建议讨论：是否允许在 core/access 的遍历边界增加最小的可选路由视图与访问生命周期接口，默认仍使用当前行为，由 app 层原锁/事务服务提供已提交视图与隔离。具体接口需讨论确定后才能实施。
如果用户坚持完全不加 core 扩展，应先共同确定能保持原局部并发和回滚语义的接入方式，而不是悄悄降级。

## B002：旧工具来源身份与新 Tools 的重名规则

状态：已记录差异；优先沿用原有来源别名机制，不能随意改名或抛弃重名工具。

- 旧 `extensions/foundation/capabilities/tool_collector/module.py:6` 按 node_id 与 reference 生成稳定 ID。
- 旧 `python/datanet/core/module_tools.py:39` 为来源和工具生成稳定模型别名，并保留 origin/via。
- 新 `domain/tool.py:79` 对不同对象同名报错。

多个节点安装同一业务模块时，这项必须按原来源身份/调用路由移到内置工具发现模块或原适配边界。
不改 core 重名规则、不把两个来源合成一个工具、不丢弃来源与撤销检查。若沿用原方案仍有不可兼容处，再讨论。
