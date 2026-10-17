# 当前交接状态（2026-10-18）

实现、最终核对与实测均已完成，准备本地提交。前两个应用未处理，不要重新启动生成队列。

- 已有提交321fb44、1ffa62c；后续最终提交会保存全部Agent组件、配置和测试证据。本轮不push。
- extensions/generated_town包含12个Agent制作组件，来源摘要逐文件可核对。Codex只写通用核心/SDK/宿主/UI/测试及JSON装配，没有业务补丁。
- configs/npc_town/network.json是31节点65连接的完整预设，9场所、7 NPC、一个观察者，另有出生模板。
- 一天真实运行5/5闭环成功，35次NPC活动，109.007秒活动执行时间；第一拍后后端冷关闭，四拍沿原会话恢复。7个会话进入专用Harness左栏原生列表。
- 最小真实出生2/2拍通过：悦创建林念，下一拍孩子加入，独立会话与记忆。
- 一天用量未缓存255978/缓存2304128/输出53809；按用户旧谷价表约0.5173元。出生约0.0477元。开发生成成本另算。
- 口语存档首轮验证通过，但审计发现也参考了旧实现；时钟、资料、存档部分会话有旧源码读取请求。本轮不是隔离源码盲测，不能再声称无答案参考。未发现工作副本外写入。
- GUI实际通过：编辑/差异/验证/发布/挂载/单拍；31节点预设源码可查看；快速拖动逐帧6条边不消失。
- 新增通用配置文档资源追踪，常识/地图/人格随核心快照恢复；原生工具历史跨重启保留，权限每次重新检查；可选拒绝说明回调不绕过权限。
- 桌面快捷方式已直连E盘EXE，参数指向build/studio/workbench-demo + configs/npc_town/network.json，无PS包装。该目录尚为空存档，第一次启动载入配置。
- 旧desktop-channels-20261017客户端PID39940已核实后关闭；本轮制作客户端PID37756保留供看会话，home在build/studio/town-from-empty/maker-client/home。不要关闭个人客户端。
- 每个制作问题最多20次/每轮450–600s；实际均远低于上限。没有重置卡。

主要文档：docs/COMPONENT_STUDIO.md；docs/applications/npc_world/COMPONENT_STUDIO_TEST_20261018.md、COMPONENT_PROMPTS_20261018.md、AGENT_TEXTS_20261018.md、COMPONENT_STUDIO_EVIDENCE_20261018.json。

最终结果：7项generated-town集成、43项工作室/核心、11项前端通过；原生工具压缩5组断言通过；三个桌面场景通过（高速拖动、工作室闭环、完整小镇/源码/网络文档编辑）。最后保存本地commit并启动桌面，不再重复付费测试。

追加修正：local.action_rules 1.0.1由原Agent分支编写cost_per_unit；生产/休息配置true，按数量计费。原始一天使用1.0.0，修正单独公开工具回归，报告已区分。网络文档/Agent执行配置入口为通用UI，不是小镇适配代码。

---

以下为历史实施记录，里面“正在运行”“待完成”均已被上面的当前状态取代。

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

## 后续进展

- 第二个提交1ffa62c保存了通用原生执行端口、SDK声明式加载、配置初始化和历史复用。工作室/原生协议13项、核心信号20项+频道后端1项、前端11项通过。
- 第二批全部通过：agent.activity、resident.context、place.move、social.same_place；时钟1.0.1已修第一格。time.text/action.points/entity.profile等7个组件源码原样复制到extensions/generated_town，component.json/provenance.json是装配配置，没有注册胶水。通用导出工具scripts/studio_export_library.py可重复导出库。
- configs/npc_town/network.json已有纯配置基本镇：9地点、7居民、脉冲/时间/存档/根共20节点54连接。家庭和场所业务还没接。profile.json有选择和API预算。代码生成脚本只用于写JSON，没有加入运行链。
- 已用独立SDK（不加载工作室）从该配置装配54个模块。矿工矿坑→铁匠铺成功，AP10→7，prepare现场出现老铁和新相邻地点，开场白未重复。没有模型调用和任何手写业务适配。
- 道路连接channels=[town.local,map.road]；人物在场双向连接channels=[town.local]。move.presence_channel=town.local，road_channels=[map.road]。context.presence_channels=[town.local]且仅识别Agent，不把业务节点当人；road_channels=[map.road]避免把业务当相邻地点。此配置保持强度2本地业务/邻地移动/同场NPC机制。
- 第三批正在运行（终端4152）：chance.events和savepoint.counter已通过发布；family正在生成。输出phase3。第四批通过同一工作室HTTP连接排队（终端29345）：rules和transfer正在生成，输出phase4。每项540/600秒，自动验证失败最多2次回传。
- 注意这一轮旧版批处理脚本在自己队列结束时会关闭宿主，可能取消第四批外接任务。已修未来脚本为关闭前等待所有native jobs，但当前旧进程不会热更新。若第四批因宿主关闭中断，保留其workspace/session，重开同一宿主后沿原历史resume/fork继续，不重新做已完成部分。不要把这当模型能力失败或无限重试。
- 原生执行器已复用NativeCheckpoints；现又转发核心committed通知给原生协调器，让纯网络状态变化也更新带上下文游标的恢复点。需要最终运行验证，不能声称硬中断均已覆盖。
- UI已加新会话/继续/分叉选择，前缀变化拒绝复用；usage增加baseline/delta，分叉的累计token不能和父会话重复相加。
- 桌面main支持--workspace和--network普通参数；Shortcut尚未更新。host已支持initialNetwork并从development/extension.json读取selection，但development包尚未引用generated_town，最终接线时补配置。
