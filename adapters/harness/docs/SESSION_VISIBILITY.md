# 客户端会话显示

DataNet 通用 Agent 与讨论成员创建为客户端可显示的普通会话，标题为 `DataNet · 节点ID`。会话开始运行后显示在侧栏，可点击打开对话及工具记录。当前按客户端默认顺序显示。

每个 Agent 仍由 Harness 的 Agent registry 运行，拥有独立会话与提示词；parentAgent 保留运行时归属。DataNet 管理范围与工具权限保持由节点授权决定。创建事件通过已有 Agent 作用域识别 DataNet 成员，避免将其重复装配为根。

会话标题使用官方 sessionTitle 服务保存，恢复时重新命名。已有 origin=subagent 的旧会话保留其历史分类；本版本新建的会话采用普通分类。旧测试实例的数据不导入日常客户端。
