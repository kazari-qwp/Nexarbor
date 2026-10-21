# 先完成一个小闭环

表中“Skill 名: 路径”通过对应 Skill 的 read_skill_reference 读取；不带 Skill 前缀的路径属于 make-components。工作副本同名教程从这些资料生成，不单独维护。

1. list_files 看当前副本，catalog_modules 按职责搜索能力，先判断复用和配置方案。
   能复用时读 nexarbor-basics: references/lessons/08-reuse.md，可直接交付配置书签，不必制造新代码。
2. 写清最小行为和验收点，读当前需要的一篇教程，不先看整套框架。
3. 完成正常流程，再补错误、权限、重复、并发测试，调用 validate 看真实结果并修复。
4. README 说明装配、可调参数和触发方式。通过配置和前端区分场所，别为每个 NPC 写一份组件。

| 当前任务 | 按需读取 |
|---|---|
| 固定入口、ctx、本地数据和状态 | nexarbor-basics: references/lessons/01-local.md |
| BFS节点对象表、跨节点访问、信号与改边 | nexarbor-basics: references/lessons/02-network.md |
| 多节点锁、并发与失败恢复 | nexarbor-basics: references/lessons/03-locks.md |
| 大文件输入、批量传递与精简回执 | references/lessons/04-tools-ui.md |
| Agent 工具、依赖与配置前端 | references/lessons/04-tools-ui.md |
| 节点引用、复制后的身份和配置 | references/lessons/04-tools-ui.md |
| 使用真实运行时验证组件 | references/lessons/05-tests.md |
| 从用户效果需求设计，在当前网络副本内试装 | inspect-network: references/测试环境.md |
| 人格、资料、事件、尾部快照与文件来源 | nexarbor-basics: references/lessons/09-context.md |
| 可发现的宿主能力及只读文件端口 | catalog_ports；nexarbor-basics: references/lessons/14-host-ports.md |

模块作者先读基础概念中的01。详细参数以依赖的 module.json 为准，别凭模块名称猜接口。
