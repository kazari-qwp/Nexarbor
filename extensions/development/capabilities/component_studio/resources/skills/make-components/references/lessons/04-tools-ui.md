# 一个包提供模块与工具

先实现公开操作，再引用：
```json
"agent_tools":[{"id":"inspect","name":"查看资料","description":"查看本地点公开资料。","operation":"read"}]
```
operation 必须已声明，参数模式复用操作；沿当前网络执行，不增加权限。requires 是同节点直接依赖，框架递归装配、去重、复用已有配置状态。图标只数一层。不要往 offered_tools 重复保存模块工具。

工具制造模式至少有一个静态 agent_tools；动态收集器用 tool_provider:{list,invoke}，list({}) 返回 id/name/description/parameters，invoke 接收 tool_id/arguments。两种提供方式不混用。框架可能给工具分配内部别名；业务名称和来源用于说明，内部别名不适合当用户可读名称。旧会话中的工具声明不代表当前可用，停用通知只说明真实变更，不应把恢复历史声明当成再次停用。

默认结果只给下一步需要的摘要、计数和引用；长列表可分页，完整正文按引用再取。写入通常返回成功数量、版本或位置，不重复回传整份原文。输入参数也要精简：大文件和批量记录传路径或引用，由代码读取、解析、写入与校验；模型不重新转写原文或逐行拼记录数组。仅有数组写入接口时，检查是否还缺少承接文件的组件。

资源名称、数量、价格、成本、条件、频道放 config_schema，写中文 title/default/约束。用同一生产组件配置木材和矿石；不要用任意 Python 表达式或宿主 RPC 假装通用。

客户端自动生成 Schema 配置表单；集合加减行等复杂交互再声明 frontend:{entry:'ui.html',title:'中文配置',height:360}，按需读 FRONTEND_GUIDE.md。前端只编辑本模块配置、展示状态，不复制业务、不改授权、不取令牌。

配置/状态的节点引用标 format:'node-id'，数组在 items 标注；网络复制据此重映射内部引用。
