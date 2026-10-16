# 显式节点模块

核心 `Node.modules` 保存 `{模块ID:{config:{...},state:{...}}}`。普通 Node、AgentNode、文本、脉冲均可挂载；核心不认识 world.* 等应用名字。参数、状态必须为 JSON 对象。

组件的服务注册函数调用 `services.node_module(id, factory)`。核心为已加载节点实例化显式声明的模块，先建立所有实例，再执行 install；带 Application 时按 bind_order 执行 bind。注册模块定义不会对未挂载的节点生效。

继承 NodeModule：install 安装本地工具，bind 连接运行时服务，close 释放监听器/信号响应器等运行资源；unmount 在显式拆除时清理持久绑定，再调用 close。用 self.tool 声明工具，它会记录所有权并检查组件仍启用。卸载后已缓存的函数引用也拒绝执行。监听器用 self.listen，close 自动解绑。自定义 close 应调用 super().close()。

可信宿主使用 `backend.modules.mount(node_id,id,config,state)`、`unmount(node_id,id)`，之后通过核心 save/现有事务提交保存；不自动向 Agent 开放这些权限。创建一组关联节点时可 mount(...,bind=False)，全部结构就绪后由宿主 bind(application)。当前配置的跨节点引用由各模块校验/使用；宿主不能在仍被业务引用时任意删除依赖节点。

序列化保存每个节点的 modules，恢复时重新安装函数/监听器，运行时代码和对象不进入 JSON。模块实现缺失时明确拒绝恢复，不猜测旧类型或自动兼容。后续保存仍复用核心差量日志和全量快照。

通用可选组件各自独立：

| 组件 | 模块/职责 |
|---|---|
| disk_network | 读取预设 initialNetwork/initialFiles，经核心 network_initialize 初始化空网络；有存档时沿已有恢复路径 |
| node_context_sources | context.sources，显式配置上下文来源并绑定 Agent；复用 context_assembly |
| node_agent_session | agent.session，创建/恢复模型会话；复用 agent_runtime |
| node_signal_agent | agent.signal，频道响应、上下文准备、原生执行、请求上限和完成/失败记录 |
| node_clock | clock.text，按新信号推进计数、格式化文本；无需 Agent 执行组件 |

时间模块本身不要求 NPC 或小镇。信号 Agent 模块没有位置、职业、孕期或世界结算逻辑。磁盘加载是宿主入口，没有加载器图节点、Start 节点或世界构建代码。

目前 disk_network 的初始网络格式复用核心 checkpoint 文档；initialFiles 是目标相对路径到 `{component,file}` 的只读资源映射，仅首次初始化读取。恢复已有档不会覆盖业务数据。正在执行的 Agent/工具不应被宿主热卸载；先停止活动再调整结构。
