# 需要用户讨论的兼容点

## B001：锁事务与新 access 的读取入口

状态：等待式访问方向已由用户确认，见 DECISIONS.md 的 D001；实现待迁移。

保留证据：旧 `tests/test_node_locks.py:224` 使用锁服务的提交前路由快照；新 `domain/core/access.py` 直接读取节点出边、偏置与汇合策略。

用户确认改为：访问到锁定节点时等待，解锁后根据当前提交状态执行和继续传播。无需保留旧的锁期间路由快照可见性，其他事务/业务规则不因此改变。

快照以节点为单位；多节点事务成组恢复，状态恢复保持对象和绑定身份。文件与 DSH 会话位置不能遗漏。

不得用全局串行替代局部锁，不得以代理旧 Node、旧 ctx 或其他遍历后门实现。

## B002：旧工具来源身份与新 Tools 的重名规则

状态：已记录差异；优先沿用原有来源别名机制，不能随意改名或抛弃重名工具。

- 旧 `extensions/foundation/capabilities/tool_collector/module.py:6` 按 node_id 与 reference 生成稳定 ID。
- 旧 `python/datanet/core/module_tools.py:39` 为来源和工具生成稳定模型别名，并保留 origin/via。
- 新 `domain/core/tool.py` 对不同对象同名报错。

多个节点安装同一业务模块时，这项必须按原来源身份/调用路由移到内置工具发现模块或原适配边界。
不改 core 重名规则、不把两个来源合成一个工具、不丢弃来源与撤销检查。若沿用原方案仍有不可兼容处，再讨论。

## B003：原平台的频道黑名单尚无对应核心匹配能力

状态：用户已确认“沿用旧逻辑”，匹配扩展已实现，6 项频道回归通过；B003 解除，见 D004。

证据：

- 原 python/datanet/core/channel_filters.py 实现 allow/deny 两种匹配。
- 原 python/datanet/core/interface.py 第 48 行对连接调用 matches(..., channel_mode)。
- 原 frontends/network-editor/src/module-access.jsx 公开了频道模式设置，属于原平台能力。
- 新 domain/core/link.py 只支持 channel in channels；新 access.py 还在调用 link.transmit 前直接按 channels 列表过滤。

旧行为：deny 列表表示排除列出的频道，其他频道可匹配。新实现按白名单解释同一列表会反转含义；静态展开成某次已知频道全集不能完整替代动态行为。

当前扫描没有发现三个应用 JSON 显式启用 deny；这是完整平台功能迁移的差异，不应宣称三个应用当前配置已因此失败。

已实施：Link 增加 channel_mode，access 统一调用 Link.allows 匹配；Module 和工具发现支持模式，模块黑名单根据当前声明的频道全集解析。默认 allow，保存恢复包含连接模式。前面的旧实现描述作为差异发现时的证据保留。

## B004：上下文来源的实际访问路径未由 access 提供

状态：已由用户明确决定解除，见 D006。用户拒绝扩展 access 传网络路径，改为按遍历顺序收集 Markdown 文件地址。

证据：

- 原 extensions/composable/capabilities/context_assembler/module.py 的 collect 读取 reached.path，并写入每项来源的 path。
- 同目录 ui.html 的预览直接展示 s.path.join(' → ')，属于实际前端功能。
- 原 python/datanet/core/network.py 的 walk_states 记录从起点到目标的节点 ID 路径；多路汇入时使用同层最先到达的那一条，强度仍按汇合策略计算。
- 当前 domain/core/access.py 的 _layers 只保留 (Node, remaining)，方法只能获得 Node，没有真实路径。

原拟议的 with_path 方案已被用户否决，不实施。现有 @access 顺序用于收集文件地址，来源预览同步显示文件地址。四路 patch、来源身份和串联规则已迁移，不恢复 ctx，不在业务模块另行寻路。

## B005：内存数据节点与 Saver 强制文件路径冲突

状态：用户已确认改为真实文件存储，见 D007；ValueNode 的文件实现与 7 项行为测试已通过，B005 解除。

证据：

- 原 extensions/storage/capabilities/value/python/datanet/components/nodes/value_node/value_node.py 的 _value 是 deepcopy 后的内存值，文件路径字符串也只是普通值，不读取文件。
- 同目录 codec.py 的 encode 直接将 node._value 写入 parameters.value，不创建源数据文件。
- 新 domain/core/saver.py 把 path: Path 定义为每个 Saver 必须实现的抽象属性；DataNode 又要求一定提供 Saver。
- 当前 app/network_saver.py 也统一按源文件路径编码数据，不过此应用层保存实现已经获准替换为原持久化编排。

此前建议下移 path 的方案不实施。按用户最新决定，ValueNode 改为真实 JSON 文件存储，Saver 接口不变；这是用户授权的存储语义变化，不再要求保持旧内存/内联形式。

现已有真实源文件，False 保存路径引用、True 复制文件均已验证。旧内联值的应用模板和配置仍待转换为独立 JSON 资源。
