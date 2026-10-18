# 先完成一个小闭环

1. list_files 看当前副本，catalog_modules 按职责搜索能力，先判断复用和配置方案。
2. 写清最小行为和验收点，读当前需要的一篇教程，不先看整套框架。
3. 完成正常流程，再补错误、权限、重复、并发测试，调用 validate 看真实结果并修复。
4. README 说明装配、可调参数和触发方式。通过配置和前端区分场所，别为每个 NPC 写一份组件。

| 当前任务 | 按需读取 |
|---|---|
| 固定入口、ctx、本地数据和状态 | lessons/01-local.md |
| 跨节点访问、信号与改边 | lessons/02-network.md |
| 多节点锁、并发与失败恢复 | lessons/03-locks.md |
| Agent 工具、依赖与配置前端 | lessons/04-tools-ui.md |
| 使用真实运行时验证组件 | lessons/05-tests.md |
| 组装网络、频道与权限 | lessons/06-presets.md |
| 从用户效果需求设计，在当前网络副本内试装 | lessons/07-environment.md |

模块作者先读 01；网络预设 Agent 先读 06。详细参数以依赖的 module.json 为准，别凭模块名称猜接口。
