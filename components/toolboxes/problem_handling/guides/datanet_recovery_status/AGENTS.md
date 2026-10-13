# 恢复状态与次数预算

datanet_recovery_status 查看恢复后的 Agent、讨论进度、反馈历史、中断操作和恢复次数预算。此查询只读，不重放执行，也不表示已有问题已解决。

agents 中 session_id、kind 可能为 null：这是旧记录中未保存的字段，不代表运行成功或失败。新创建的根 Agent 保存真实会话ID；其他缺失的可选字段明确用 null 或空列表返回，接口不返回 undefined。

recovery_budgets 给出目标、状态、attempt_count、max_attempts 与 remaining_attempts。查询和读取历史不启动恢复，也不消耗恢复次数。具体恢复规则由框架在拥有自主排障授权的 Agent 首次进入问题通道时提供。

本次源码变更尚未运行测试，也未打包安装到客户端。
