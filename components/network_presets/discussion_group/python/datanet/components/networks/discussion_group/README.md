# 小组讨论网络

Leader、Recorder 固定各一名，普通成员数量通过 `member_count` 指定，默认3，范围1—64。每人拥有独立会话和个人 Markdown 记忆。

在 Harness 中通过 `datanet_create_network` 创建并用 `datanet_discuss` 调度；使用说明见本组件根目录的 AGENTS.md。讨论成员使用 submit_round 或 skip_round，每轮共享相同的上轮发言快照；Recorder 维护请求尾部公共笔记并归档成果。

网络包保存一个普通成员模板，创建时由通用模板展开器生成成员、连接和引用。Python 装配入口 `build_discussion_group(member_count=3)` 使用同一展开器，只装配网络，不请求模型。
