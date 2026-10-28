# Nexarbor 项目结构与机制说明

Nexarbor 是可视化 Agent 应用开发平台。节点表达对象，模块表达能力，连接与频道表达访问关系。应用自己的规则、工具、数据和会话保存在项目目录中。

当前目录 `E:\项目_手动重构` 是对原项目的模块化重构。工程采用四层：`domain` 定义对象和规则，`app` 编排运行与持久化，`adapt` 连接 DSH、文件和通信，`frontends` 提供桌面与编辑器。核心不是旧实现的兼容包装，原业务模块通过新对象和 `@access` 运行。

## 目录

```text
 domain/core/               节点、模块表、工具箱、连接、访问、数据抽象
 domain/agent/              AgentNode、记忆策略、输入
 domain/signals.py          信号值对象
 modules/tool_discovery/    内置串联工具发现
 modules/context_assembler/ 内置上下文组装及四路策略
 app/runtime/               后端、信号/脉冲、执行绑定与运行服务
 app/transactions/          节点锁和事务
 app/persistence/           表恢复、状态日志、资源快照与检查点
 app/studio/                工作台、模块加载/验证/副本/发布/测试
 app/projects/              项目装配和宿主端口
 adapt/harness/             DSH会话、模型连接、工具和制作Agent宿主
 adapt/communication/       RPC/HTTP和组件前端桥
 adapt/files/               文件路径、原子写入等平台边界
 frontends/desktop/         Electron桌面入口
 frontends/network-editor/  React网络工作台
 frontends/shared/          编辑器与制作图片共用的纯数据逻辑
 projects/                  讨论协作、资料库、小镇及工作台模块
 resources/studio/skills/   两种制作Agent使用的四个渐进Skill
 resources/examples/       新小镇初始学习范例
 项目演示/                  三个应用的初始与最终状态
 docs/migration/            迁移决定、原文件清单、验收和成本证据
 tests/                     本地行为与原生DSH集成测试
 scripts/                   迁移与应用验收入口
```

## 普通节点与装配

`domain/core/node.py` 的 `Node` 组合 `NodeInfo`、`Modules`、`Tools`、`Links`，另有偏置与汇合策略。普通节点不含 Dataer 或 Agent 循环。

- `NodeInfo`：ID、名称和说明。
- `Modules`：按标识保存模块实例，持有这些模块工具箱的聚合入口。
- `Tools`：递归持有工具或工具箱。`for tool in tools`、`list(tools)` 直接展开，按成员顺序深度遍历。相同工具对象去重，不同工具同名报错。
- `Links`：管理实际出边。`Link` 持有目标ID、频道、阈值与处理器，默认处理器按倍率相乘。
- `Installer`：递归安装声明依赖，卸载被依赖项时拒绝；移除模块会摘掉其工具箱，保留已安装依赖。

`_add/_remove` 是容器内部操作，外部通常调用 `node.install/remove`。`Modules.copy()`、`Tools.copy()` 只浅拷贝容器；完整节点/网络复制由 app 和前端重映射ID与文件，恢复已有表，不检查或补装依赖。

## 访问边界

模块继承 `Module`，公开操作需要跨节点时使用 `@access`。方法只描述对单节点的操作，装饰器负责遍历并返回 `{节点ID: 结果}`：

```python
from domain.core import Module, access

class ReadNumbers(Module):
    def __init__(self):
        super().__init__('read.numbers', channels='a', strength=2)

    @access()
    async def read(self, node):
        if node.node_type == 'markdown':
            return int(node.dataer.read())

# await module.read() 得到节点ID到结果的映射。
```

前端节点属性中的模块默认强度只用于装配时未配置强度的模块；装配后模块保存具体值，修改节点默认值不联动已装配模块。这是前端元数据，core不持有继承关系。

省略装饰器参数时继承模块的频道和强度；对象没有设置时只在本节点执行一次。显式空频道仅访问本节点。异步操作广度分层、同层并发，整层结束后继续；节点去重。频道可采用白名单或黑名单。

边检查频道和入口阈值，再处理强度。目标节点汇合多路输入并加偏置；负强度不再执行。默认求和，也支持 max、min、average。遍历遇到被锁节点会等待解锁，然后读取当前提交的节点和出边。拿到对象之后直接使用，不在各模块再次寻路。

信号由 `app/runtime` 的独立运行器负责，保留原同层延后工作、闭环回源、取消、预算和保存语义，不复用 `access`。归属或前端亚节点展示本身不授予访问权限，管理也需要显式连接和频道。

## 数据与Agent

`DataNode` 继承普通节点并组合 Dataer、Saver 和 `save_data`。Dataer操作具体数据，Saver声明资源与保存办法。Markdown Dataer直接读取/修改真实文件，并支持局部替换和追加。普通文本工具的原子写入与 `.bak` 备份在 app 实现，不挤进核心。

`save_data=False` 保留外部文件引用；为True时，网络保存流程复制真实文件。它不意味着从内存生成一份文本。资料库 Value、CSV、SQLite、Collection、Catalog 和向量节点都继承现行 DataNode，各自持有资源。

`AgentNode` 是节点类型。`MarkdownAgentNode` 同时继承 AgentNode 与 MarkdownNode，使用Markdown记忆策略；其他节点组合采用空记忆策略。Agent提供自身记忆工具、输入和工具发现入口，模型运行通过注入的执行器完成。工具发现跳过其他Agent的工具；普通上下文只读取Markdown节点。

资料库中，目录登记集合及路由，各集合独立保存正文、版本和索引。原文归档为Wiki，RAG目录返回Wiki链接和版本化定位；Agent仍可直接访问已授权的信息节点。

## 上下文与工具

`modules/context_assembler` 按 system_prompt、context、inputs、tail 四个策略组织来源：系统规则、持续资料、一次性输入和动态尾部。串联与四路收集共用实际访问顺序，返回Markdown文件地址作为来源。事件输入保留身份与确认语义，避免重复消费。

`modules/tool_discovery` 返回可迭代Tools，可串联另一个发现器。原执行器直接迭代工具、调用所得工具引用；不恢复旧来源目录或中继调用层。

制作Agent的四个入口为 nexarbor-basics、inspect-network、make-network、make-components。正文与参考按需读取，观察、工作分支、验证、发布、Git和委托沿用原工作流。模块亚节点是72×28名称矩形，频道进入悬停/模块详情，不是可执行节点。

## 运行、锁与保存

`app/runtime/backend.py` 组合网络与服务；`app/projects`/`app/studio/project.py` 加载项目清单、节点和实际模块工厂。模块源码、清单和辅助策略放在同一个模块目录。

节点锁保护局部访问与修改，多节点事务成组提交或恢复。快照覆盖节点状态、表、边、文件、执行绑定和会话位置，保留对象身份；不以全网串行代替局部并发。

状态日志、检查点与资源由app编排。DSH保留原生JSONL会话；适配层保留会话ID、前缀校验、消息投影、压缩和上下文导入/分支。普通冷重开接续实际持久日志头，显式回滚或导入仍使用指定前缀。pending/uncertain操作保留人工核对机制，不盲目重放工具副作用。

Git Commit保存网络、资源和原生上下文位置。复制Agent得到独立会话；导入已保存网络从保存位置建立独立分支。模型默认显式high，所有入口请求上限10000，实际请求事件由适配层交给相关业务模块。

## 三个应用与阅读顺序

1. 先读 `domain/core/node.py`、`tool.py`、`module.py`、`installer.py`、`link.py`、`access.py`，理解对象组合和访问规则。
2. 再读工具发现与上下文组装器，查看最直接的跨节点操作。
3. 读 `domain/agent` 和一份DataNode实现，理解能力如何组合，而不是继续扩展普通Node。
4. 按需要进入app的运行、节点锁、持久化、项目加载；模型协议和前端细节留在适配层。
5. 以三个实际应用模块和初始/最终项目检查行为与成果；成本、限制、原始命令和实测范围保存在 `docs/migration`。

应用一保留讨论、协作与真实Git交付；验收顺序为提出验收请求并提交脚本/结果、通知全员、失败打回或通过发布、成员收尾。应用二保留原六阶段任务与反馈，验证真实语义检索、原文和版本。应用三是具有地点、道路、交易、协议、家庭与记忆的小镇，已完成五天25时刻，并在同一状态上追加概率事件，从真实前端续跑至第六天30时刻，成果与历史可在前端查看。

当前按用户收缩范围完成三个应用、核心与约定前端的迁移；额外未使用模块不再迁移。逐文件处置与实际验收范围见 `docs/migration/DELIVERY.md`，不把文件索引称作逐行语义审查。
