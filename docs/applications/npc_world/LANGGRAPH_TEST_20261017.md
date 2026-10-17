# LangGraph 后端与事件执行图验证

2026-10-17，使用官方 langgraph 1.2.16，本地 .venv Python 3.11。未调用付费模型，未运行完整真实 Agent 世界，未修改既有六天存档。

## 已完成

事件触发器匹配事件/频道/条件，模块执行器解释结构化配置，官方 LangGraph 负责顺序、条件边、并行及汇合。旧 signal_response 已移除。时钟、Agent 活动、存档计数器直接使用新组件；核心仅为应用事件补充 emit_async，并阻止同步事件错误丢弃异步结果。核心信号传播算法未改。

## 测试结果

| 测试 | 项数 | 结果 |
|---|---:|---|
| test_event_trigger_components.py | 5 | 通过 |
| test_module_execution.py | 5 | 通过 |
| test_npc_world.py | 13 | 通过 |
| test_neighborhood_inputs.py | 6 | 通过 |
| test_context_assembly.py | 5 | 通过 |
| test_core_signals.py | 20 | 通过 |
| test_node_modules.py | 6 | 通过 |
| 合计 | 60 | 全部通过 |

新增执行图测试实际调用上游库，并非模拟其调度。覆盖嵌套并行分支长度不等、条件分支未激活不参与汇合、默认分支、执行结果引用、第二次调用状态隔离、未授权操作拒绝、解绑后后继拒绝、另一命名绑定保留、普通同步/异步事件、配置保存恢复、重复绑定无重复监听器，以及两个同步线程超时后逐个退出仍禁止提前重入。

小镇临时配方：成功移动发出 node/tool-invoked，触发信息收集和工具装配并行，全部结束后组装上下文；验证地点已更新、旧本地信息消失、拿到铁匠铺工具，无效移动不触发。该配方仅用于本次集成验证，不改变默认预设的行动规则。

小镇回归覆盖脉冲→时间文本→同层并行 NPC→存档计数→回源，五次显式全量存档、重复信号、失败成员隔离、恢复后继续、婚姻生育新增儿童等。

原生 Harness native_npc_pulse_test.cjs 使用 Mock 模型，普通与 DATANET_DURABLE_TEST=1 两种模式均通过。持久模式验证七个原生会话的日志位置、仅拓扑变化保存、纯上下文游标更新、第五次信号全量提交延后到工具结果落盘、直接移动正常结束并回源。没有模型 API 调用。

另用导入拦截器使 LangGraph/LangChain 不可导入，核心 Backend 仍能独立启动关闭，证实新依赖没有进入核心。

## 范围与构建

本次交付为源码组件封装，安装官方依赖后已验证源代码运行。Windows 构建脚本已支持组件声明 python.collect/python.metadata 收集第三方依赖；本机 .venv 未安装 PyInstaller，发行 EXE 构建尝试在启动 PyInstaller 前停止，没有生成或发布新发行包。后续重打发行包需先装构建工具和启用组件的 requirements。

普通应用事件需在业务事务成功后发布，不承诺回滚已经完成的副作用。同步 Python 线程不能强杀；执行器在其退出前拒绝同节点重入。调用方仍需为普通事件选择合适的截止时间。

使用接口见 [EVENT_EXECUTION](../../EVENT_EXECUTION.md)；组件描述与文案审阅见 [TEXT_REVIEW](LANGGRAPH_TEXT_REVIEW_20261017.md)。
