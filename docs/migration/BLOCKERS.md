# 需要用户讨论的兼容点

## B001：锁事务与新 access 的读取入口

状态：按 D001 的等待式访问、节点局部快照及执行器门禁已迁入并验证。新 Backend/原增量日志和三个原节点事务杀进程断言已接入并通过（234 项回归）。完整 Studio/组件宿主仍待接入；当前无待用户答复的兼容问题。

保留证据：旧 `tests/test_node_locks.py:224` 使用锁服务的提交前路由快照；新 `domain/core/access.py` 直接读取节点出边、偏置与汇合策略。

用户确认改为：访问到锁定节点时等待，解锁后根据当前提交状态执行和继续传播。无需保留旧的锁期间路由快照可见性，其他事务/业务规则不因此改变。

快照以节点为单位；多节点事务成组恢复，状态恢复保持对象和绑定身份。文件与 DSH 会话位置不能遗漏。

不得用全局串行替代局部锁，不得以代理旧 Node、旧 ctx 或其他遍历后门实现。

## B002：旧工具来源协议与新 Tools

状态：按 D010 取消保持旧工具来源/别名/中继调用协议的迁移方案。执行器直接 for/list 使用 discover() 所得 Tools，直接调用取得的工具引用；access 已完成可达性判断，不重复检查。core 重名规则不变。

先前为保留旧协议增加的 collect/invoke 与 ToolCatalog 尚未接入实际执行器，已撤回。多个实际应用如何声明工具，随真实装配迁移；遇到具体冲突先记录讨论，不擅自修改新设计或偷偷绕开 Tools 的迭代规则。

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

## B006：同归属树的无连线模块调用与新 access 冲突

状态：已由用户选择不保留而解除，见 D008；未修改 core，未添加 family 模式。

旧 module_requests.py 的 local_call 和 tests/test_subnodes.py 允许 parent→sub 无业务边调用；新 access 的空频道仅执行本节点，不读取 parent_id。复现得到 {'owner': 'owner'}。

用户决定采用新规则：归属本身不授予访问权。原捷径和相关正向许可断言不迁移，旧项目需要显式配置真实连接/频道。新增 test_no_implicit_family_access.py 验证归属、错误频道和不足阈值都不能授权；真实边通过后才调用。


## B007：信号层生命周期与当前 access

状态：按用户最新决定 D015 解除。撤回 D014 的共享方案和可选去重；信号不复用 access，不再等待核心层生命周期接口讨论。

原 SignalRuntime 的同层 LayerWork.drain、脉冲 close_loop 回源回执以及预算、取消、故障、保存规则，由独立 app 信号运行器迁移。access 恢复原有去重访问行为，已有门禁与节点快照保留。独立运行器仍未完成；来源与边界见 SIGNAL_BOUNDARY.md。


## B008：旧成员提交接口允许 key，但旧 Git 提交接口禁止 key

状态：等待用户选择。真实付费验收已停止，不自动重试。属于原项目已有契约矛盾，未确认涉及新核心限制。

来源：projects/discussion-collaboration/modules/collab.participant/module.json 的 submit.parameters 包含 key；module.py 会把 activation.parameters 全部复制并转发。git.integrator.rev_2863bbe53e.rev_c376775a7e/module.json 的 submit.parameters 仅 member/commit/branch，additionalProperties=false；旧 python/datanet/core/local_modules.py NodeModule.install.call 在执行前也校验该 Schema。

最小提案：成员入口消费/不转交 key，Git 仍按原 commit 判断 duplicate；不增加新幂等规则。补丁已准备但尚未应用：build/participant-submit-key-proposal.patch。因用户要求迁移不得擅自改变原业务，已请求明确选择。参见 evidence/2026-10-27-discussion-api-stopped.json。
