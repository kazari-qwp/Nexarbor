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

状态：待讨论；未修改 core 的频道规则。

证据：

- 原 python/datanet/core/channel_filters.py 实现 allow/deny 两种匹配。
- 原 python/datanet/core/interface.py 第 48 行对连接调用 matches(..., channel_mode)。
- 原 frontends/network-editor/src/module-access.jsx 公开了频道模式设置，属于原平台能力。
- 新 domain/core/link.py 只支持 channel in channels；新 access.py 还在调用 link.transmit 前直接按 channels 列表过滤。

旧行为：deny 列表表示排除列出的频道，其他频道可匹配。新实现按白名单解释同一列表会反转含义；静态展开成某次已知频道全集不能完整替代动态行为。

当前扫描没有发现三个应用 JSON 显式启用 deny；这是完整平台功能迁移的差异，不应宣称三个应用当前配置已因此失败。

建议讨论：是否允许沿用原 allow/deny 匹配规则，为 Link 增加模式设置，并让 access 统一调用连接的匹配方法而不重复预判。allow 作为默认值，现有行为保持。若不保留该功能，需要用户明确确认范围变化。
