# 组件装配与知识库验证

本次使用源码后端验证，未重新打包发布。真实 Harness 测试使用本机原生 AgentLoop 和桥接代码，生成模型由本地响应替身提供；未调用付费生成 API。

## 验证范围

| 测试 | 结果与覆盖 |
|---|---|
| 第一阶段回归 | 95 项：94 通过、1 二进制独立入口跳过；组件拆分、工具授权、讨论、协作、消息、持久化 |
| 知识库与组件最终定向回归 | 13 项通过；随后新增的根预设依赖完整性测试通过，组件解析合计 5 项通过 |
| 最终依赖调整后全量回归 | 106 项：104 通过、2 项跳过（二进制、单独运行的本地嵌入测试）；140.432 秒，日志 components-knowledge-regression-final.log |
| 原生 Harness 共享运行时 | modular_shared_runtime_test.cjs 通过：尾部快照、工具变更、文档与权限 |
| 原生 Harness 协作 | modular_cooperation_test.cjs 通过：两类小组重复任务、报告和独立会话 |
| 原生 Harness 知识库 | native_knowledge_base_test.cjs 通过：归档、直接读取、路由复用、两个固定 Agent、只读检索权限 |
| Wiki | 实际 MkDocs 构建通过，生成页面与站内搜索索引 |
| 语义检索 | 实际 LlamaIndex + 本地 BAAI/bge-small-zh-v1.5 测试通过，覆盖中文检索、更新、删除和重启 |

知识库测试还覆盖四类数据读写、完整取回、版本去重、来源变化提示、混合批次、原文件留存、结构化统计、写入中断恢复、图恢复和两个应用共存。未进行真实模型的自动分类质量评估，也没有运行完整历史付费工程任务。

## 本地性能样本

- 1000 条 SQLite 记录批量写入：7.448 秒。
- 20 次直接筛选查询：p50 1.753ms，p95 2.165ms。
- 20 次按 ID 读取：p50 1.377ms，p95 1.901ms；上述直接操作不调用模型。
- 本地中文嵌入冷加载及两份文档导入：26.384 秒。5 次热查询 p50 12.36ms，最大 13.06ms，CPU 两线程。

这些是本机小数据集测试，不代表大库性能或生成模型的总响应速度。模型下载和可选依赖安装不计入查询耗时。

测试日志与指标位于忽略的 build/ 目录：components-knowledge-regression-final.log、knowledge-final-targeted.log、knowledge-semantic-metrics.json、knowledge-direct-metrics.json。
