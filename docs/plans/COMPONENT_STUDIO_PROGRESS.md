# 小镇组件制作试验：执行记录

本轮只测试第三个应用。业务组件由DeepSeek Harness原生制作Agent写，Codex仅维护通用框架、工作室、配置、文档和验收代码。不由Agent生成整张网络，不手写业务兼容补丁。全局初始化采用核心配置加载。允许付费API，具体问题最多20次修复；用户睡觉，不弹选项、不重置额度。

## 当前可回滚点

- 321fb44：组件工作室第一阶段，原生制作会话、验证、不可变发布、CodeMirror源码/差异、Electron默认启动与快速拖动修复。

## 试验位置

- build/studio/town-from-empty/host：独立工作室后端、工作副本、验证快照、发布库。
- build/studio/town-from-empty/maker-client：本轮独立Harness客户端，client-meta.json有PID和回环地址；仅此目录下客户端属于本轮。原先E:/dsh/state客户端已不在线，切到本轮独立客户端并复用已授权账户认证，未修改原客户端配置。
- build/studio/town-from-empty/requests.json：第一批简单中文提示。
- build/studio/town-from-empty/phase2-requests.json：第二批详细组件提示和时钟反馈。
- scripts/studio_make_components.mjs：通用制作队列；只传递需求、等待宿主验证和发布，不生成业务源码。
- build/studio/native-port-smoke：通用原生执行端口最小验证，两轮各1次请求，均READY；第二轮已接入原生日志位置检查点。

## 已完成的实际制作

- time.text：从空白生成，原始工作副本module-70ed79281b，原会话session-e56faa13-88a4-4956-9734-1a21da944ddc；宿主验证通过。首轮约44k输出token，包含大量测试与推理。
- action.points：module-6dfd4487fc，session-51b1add7-0e69-4af2-a7b1-62a9c77c2309；每时刻10点、检查/扣除/余额，宿主通过。
- entity.profile：module-d2cc5b3fb1，session-25fa8ae8-3fdc-4e4f-9dd3-63de4059ae3f；通用资料、金币、物品和统一元数据，宿主通过。
- time.text首格修复：同前缀分叉session-5d9b4b13-d79c-4439-979c-a68fec8ef0b1，改为tick=-1，第一脉冲第1天早上；1.0.1已发布。组件源码仍由Agent改。
- agent.activity：session-8aef108b-295c-400f-9eba-626637c9d961，等待通用backend.execute_agent正常完成，不用submit；通过并发布。

其余第二批context/movement/social正在同一个队列运行。结果文件在phase2目录。当前活动终端会话52678；每个任务540秒，双制作会话并行，验证失败最多自动回传2次。不要再启动第二个Backend占用同一SQLite目录。若需查看，在现有editor-connection.json的回环HTTP接口调用studio.*。

## 通用框架改动（未作为应用兼容代码）

- 独立module_sdk增加operations声明，NodeModules.call校验调用；transaction回滚选中模块state；refresh重绑通用生命周期。
- 可信调用者current_agent_id，核心工具调用维护principal，避免让模型传身份。
- SDK按nodeModule配置直接加载标准模块，不需要给每个生成组件手写Python注册器。
- backend initial_document从纯配置初始化空网络；不覆盖已有存档。
- 原生执行端口使用现有AgentLoop、InstructionHistory、ToolPermissions、NativeCheckpoints；按node.execution配置的prepare操作刷新四路输入和可达工具，无小镇业务分支。
- HarnessRemote支持同前缀继续/分叉历史，前缀不一致拒绝。正在补分叉token增量统计，避免把继承历史重复计费。

## 必须继续完成

1. 等第二批完成，检查README/清单/返回接口；失败只能反馈给制作Agent改，不手写业务补丁。
2. 由制作Agent补概率事件、配置驱动的资源/商店/修理/休息规则、家庭/婚姻/两天出生、计数全量存档组件。配置和依赖说明可详细给；不把旧NPC源码给他们。
3. Codex只用配置组装完整小镇：9场所，情侣、伐木工、两名不同人格的矿工、铁匠、流浪汉共7名，出生后第8名儿童；脉冲→时间→全部NPC→存档→脉冲。道路/在场town.local，tick独立world.tick。强度2，节点散度-1，门槛1。
4. 把Agent产物原样复制进可选扩展源码目录，component.json和extension.json只写配置。新SDKnodeModule入口已支持，不要写注册胶水。development默认选择/预设加载仍待接线。
5. 应用级边界测试：AP10，移动3、生产6、休息6、说话/交易1；动态现场信息，跨场所拒绝，库存/家庭幂等，出生下一轮参加，恢复。
6. 一次完整五时刻真实运行，有总API请求/时间上限；必要时修指定组件再局部复测。所有模型会话要能在Harness左侧看到。可把原生执行日志root配置到本轮独立客户端home/sessions或用通用测试查看器。
7. 再选代表组件对比详细提示与较口语提示；同前缀优先分叉历史，不能把含答案的历史当独立从零测试证据。
8. GUI验收、快速拖动逐帧回归，更新桌面快捷方式去掉旧连接JSON，许可/文档/完整最终测试和提交。不要push（本轮未要求）。

## 测试状态

前端11项通过；桌面studio闭环通过（build/studio/desktop-1792249674888）。Python工作室+原生协议11项通过。SDK模块和核心最近又有变动，仍需最后回归。快速拖动修复之前已通过；最新重建后还需重跑desktop.routing.mjs并检查截图。

注意：之前手工修订的ready_clock/ready_savepoint是早期迁移样例，不属于本轮从空白的最终小镇。最终装配只使用本轮Agent写出的组件。报告必须区分两者。
