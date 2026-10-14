# 自定义日志事件恢复修复

Harness 原生 Session.append 不接收 ignorable 标记，自定义事件此前能实时运行但无法冷读。Harness 适配层在持久化 handle.append 边界仅为 datanet/request-tail 和 datanet/request-recovery 加入 ignorable:true，保留事件正文及序号；其他未知事件仍按原生规则拒绝读取。

验证：原生 zstd 最小关闭重开测试通过；原生请求恢复测试通过。此次实际十个会话、4449条事件均可被原生存储读取并重建，重开的真实客户端 session/page 接口十个历史全部成功。用户也确认已正常打开。未调用付费模型。

旧日志已备份到 build/hone-guide-20261014-r1/original-logs-before-repair。迁移只补齐两种事件的标记，保留原生压缩分帧。测试客户端已安装补丁并保持打开；日常客户端未关闭。没有修改给 Agent 看的文档或描述。
