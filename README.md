# Data Node with Agent

[GitHub 仓库](https://github.com/kazari-qwp/data_node_with_agent)

可组合的 Agent 数据网络。节点提供数据和工具，通过不同的读取、写入连接组成有向网络；需要推理的节点可以配置独立 Agent。Python 框架包名保留为 `datanet`。

目前已实现读写网络和实验分析演示：根 Agent 调用根节点的合格率工具，工具经网络读取 CSV 实验记录和 SQLite 判定规则，再用 Python 计算并返回来源。实验记录全部为模拟数据。

## 已实现的能力

- 基础 `Node`、统一结果 `NodeResult` 和本地工具箱。
- 通用 `CsvNode`、`SqliteNode` 和内存单值 `ValueNode`，统一 write() 本地写入。
- 节点共享地址接口，分别保存强读、弱读、强写、弱写连接。
- BFS 读取、环与重复节点去重、数据类型筛选和来源路径。
- JSON 网络配置保存与加载，恢复节点参数和四种连接。
- CSV 主键读取、多个等值条件查询；SQLite 主键查询及事务写入。
- 节点默认 agent=None；绑定实例即可调用，设回 None 即移除，可保留或重置实例的会话历史。
- 模型工具调用通过所在节点的工具箱执行，不依赖全局业务注册表。
- 实验应用的模拟生成、规则初始化、网络统计与中文报告。
- 数字网络 Agent 演示：查看节点连接，从指定节点执行强读、弱读。

写入按强弱写连接路由到一个指定目标，支持 insert/update/upsert。RAG、动态记忆整理、NPC 消息传播和自主创建节点都是后续目标，不属于当前成果。

## 访问语义

连接强弱与访问范围是两个概念：

| 操作 | 范围 | 遍历方式 |
|---|---|---|
| 本体读取 | `local` | 只读取起点 |
| 弱读 `weak_read()` | `integrated` | 起点及强读连接可达节点 |
| 强读 `strong_read()` | `federated` | 起点及强、弱读连接可达节点 |

起点可以是网络中任意已注册节点。读取不会沿写连接访问，也不会修改业务数据。接口当前只有目标地址；这些列表是程序内的访问配置，尚未实现调用者身份认证、细粒度过滤和跨进程授权。

## 目录结构

```text
datanet/                         # 通用框架，不依赖实验应用
  agent/agent.py                 # Agent 与模型/工具循环
  interface.py                   # 不可变地址接口
  network.py                     # get/query 与共享 BFS
  serialization.py               # JSON v1 保存加载与配置校验
  nodes/
    node/node.py                 # 基础节点、结果与工具箱
    csv_node/csv_node.py
    sqlite_node/sqlite_node.py
    value_node/
      value_node.py
      demo.py
      demo_network.py            # 数字网络与强弱读演示
applications/
  network_demo/                  # 数字网络 Agent 与管理工具演示
    setup.py                     # 组装网络、根工具及可选 Agent
    tools.py                     # describe_node / weak_read / strong_read
    tools.json                   # 模型可见的工具描述
    system.md
    run_agent.py
  experiment/                    # 完整实验应用
    network.json                 # 三节点及四种连接的配置
    network_setup.py             # 加载网络配置并装配根工具
    agent_setup.py               # 绑定根 Agent
    configuration.py             # 实验规则节点实例
    rules.py                     # 规则查询与判定函数
    generate_data.py
    init_db.py
    run_agent.py
    tools/
      analysis.py                # 纯统计逻辑
      network_tools.py           # 经网络取得输入并计算
      direct_tools.py            # 原直接读取工具，用于对照
      tools.json                 # 模型工具描述
    prompts/report_system.md
    data/
      实验记录01/01.csv
      lab.db
    debug/                       # CSV、规则、网络演示与 notebook
scripts/                         # 兼容原 CLI 命令的薄包装
tests/                           # 本地回归测试
docs/                            # 目标、进度及历史方案
config.py                        # 统一应用文件路径
```

## 安装与运行

使用 Python 3.11 或以上版本，在自己的 Python 环境中安装：

```powershell
python -m pip install numpy pandas openai python-dotenv
```

以下命令都在仓库根目录执行。仓库已有模拟数据，可以直接运行本地演示，无需 API 密钥：

```powershell
python -m scripts.demo_network_analysis B
python -m scripts.demo_csv_node 001
python -m scripts.demo_nodes A
python -m scripts.demo_number_network
```

相应实现也可直接按模块运行：

```powershell
python -m applications.experiment.debug.demo_network_analysis B
python -m applications.experiment.debug.demo_sqlite_node A
python -m datanet.nodes.value_node.demo_network
```

节点类有统一公共导入入口：

```python
from datanet.nodes import Node, CsvNode, SqliteNode, ValueNode
from applications.experiment.network_setup import build_lab_network

network, root = build_lab_network()
result = root.invoke_tool("analyze_project", project_id="B")
print(result)
```

## 保存和加载网络

```python
from datanet.serialization import save_network, load_network

save_network(network, "network.json")
network = load_network("network.json")
```

JSON v2（兼容 v1 加载）支持基础、单值、CSV、SQLite 四种节点，保留节点顺序和四种连接列表，支持环和同一地址出现在多个列表。相对数据路径以配置文件所在目录为基准；跨盘符时保存绝对路径。加载不会打开或创建实际数据文件。

CSV、SQLite 只保存访问参数和路径，数据继续保留在原文件；单值节点保存 JSON 原生值。自定义节点类型、非 JSON 单值和非字符串 CSV dtype 明确报错。未知版本、重复节点、缺失连接目标或多余字段也会报错。保存使用临时文件替换，校验失败不会覆盖已有配置。

工具函数、Agent 实例、密钥及会话历史不写入配置；v2 保存 Agent 创建参数。加载后的节点 agent=None、工具箱为空，由应用先装配工具，再 assemble_agents 创建实例。实验应用的三节点结构已迁移到 `applications/experiment/network.json`，Python 装配层只加载配置并绑定合格率工具，不再硬编码节点和连接。

## 启用模型

在仓库根目录创建 `.env`，填写自己的配置：

```dotenv
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_MODEL=你的账户支持的模型名称
```

`.env` 已被 Git 忽略。当前实验装配使用 DeepSeek 的兼容接口和关闭思考配置，模型需支持相应参数与工具调用。

```powershell
python -m scripts.run_agent "请查询项目 B 的合格率。"
```

根节点绑定 Agent，规则和记录节点的 agent 默认为 None。每次任务最多请求 5 轮；模型返回工具请求后，根节点执行网络统计工具并回传结果。工具选择为 `auto`，模型也可能直接回答，当前尚未强制所有统计回答都有成功的工具证据。

### 数字网络 Agent

```powershell
# 直接调用根工具箱，不请求模型
python -m scripts.run_network_agent --local
# 使用同一份 .env，通过模型调用网络工具
python -m scripts.run_network_agent "从 n1 出发分别强读和弱读，列出数字并解释差异。"
```

根节点注册 describe_node、weak_read、strong_read、weak_write、strong_write 五个工具。数字节点 n1～n6 的查询键为 `value`。从 n1 弱读得到 `[1, 2, 4]`，强读得到 `[1, 2, 3, 4, 5, 6]`，结果包含来源及首次发现路径；环与重复连接不会导致重复读取。可以把起点改成 n3 或 n5。

演示根节点的管理工具持有整个网络，可选择任意已注册节点作为起点；这不是按调用者身份限制访问的权限实现。只有根节点绑定 Agent，数字节点的 agent 保持 None。

## 实验统计规则

有效记录须属于指定项目、标记为“是”，且测量值不缺失。合格率为通过数除以有效数；没有有效样本返回 `null`。

初始化规则：A 至少 80，B 在 40～60 之间，C 至多 20，均包含边界。生成器默认整数范围 0～100，支持模拟缺失值。需要重新生成或初始化时：

```powershell
python -m scripts.init_db
python -m scripts.generate_data
```

生成命令会覆盖当前模拟 CSV。重复初始化保留已有规则，不会自动覆盖修改过的阈值。

## 验证与后续目标

```powershell
python -m unittest discover -s tests -v
```

当前 125 项本地测试覆盖存储读取、条件查询、强弱范围、写连接隔离、环去重、缺失输入、网络统计、配置保存加载、工具发现与只读跨节点调用，以及模拟 Agent 调用。测试使用独立临时文件；模型响应由模拟客户端提供，不消耗 API 额度。这些是功能测试，不代表已有独立检索性能评估。

数字网络的真实 API 验证中，模型实际调用了节点描述、弱读和强读三个工具；工具反馈中的数字序列已与本地遍历结果核对。

2026-10-09 的真实 API 验证中，模型实际调用一次根统计工具，经网络取得 B 项目有效 18、通过 9、失败 9、合格率 50%。这是模拟数据快照的结果，不是固定业务结论。

完整目标见 [项目目标](docs/PROJECT_GOALS.md)，实际阶段记录见 [项目进度](docs/PROJECT_PROGRESS.md)。后续包括精确事实版本、任务恢复、RAG、基于使用反馈的记忆关联与冷热分层，以及 NPC 分圈消息传播；Agent 自主创建节点安排在最后。


## 本地写入与网络写入

三种数据节点统一提供 `write(key, value, mode="upsert")`，返回 NodeResult。insert 仅新增（已存在返回 conflict），update 仅更新（不存在返回 not_found），upsert 更新或新增。ValueNode 创建时已有 value，即使值为 None，insert 也返回 conflict；只接受固定主键 value。CSV/SQLite 的 value 为字段字典，可部分更新，未提供的字段保留；主键由 key 提供，不允许在 value 中改成另一主键。

```python
value_node.write("value", 42, mode="update")
csv_node.write("001", {"测量值": 85}, mode="update")
sqlite_node.write("A", {"lower_bound": 85}, mode="update")

result = network.weak_write("root", "target_id", "value", 42, mode="update")
result = network.strong_write("root", "target_id", "value", 42, mode="update")
```

weak_write 沿强写连接，strong_write 沿强、弱写连接；都包含起点。网络用 BFS 查找目标，环和重复地址去重，只修改指定目标一次，不广播、不沿读连接。目标不在范围内返回 forbidden，基础 Node 写入返回 unsupported，成功结果附 write_path。该范围控制仍是程序内配置，不是调用者身份认证。

CSV 校验字段和已配置 dtype 后通过同目录临时文件替换保存；现有文件/表必须存在，不自动建库建表。SQLite 使用事务处理查重与写入，字段约束失败回滚，数值类型遵循表本身的 SQLite 类型与约束。写入参数错误会抛出 TypeError/ValueError，存储错误通过 NodeResult.errors 返回。CSV 暂无多进程读改写锁，不支持并发写入；网络不提供跨节点事务，工具成功写入后，模型回答失败也不会撤销数据。

数字 Agent 演示写连接为 root 强写到 n1、n1 强写到 n2、n1 弱写到 n3。模型写工具的起点固定 root，不能自己换起点；弱写可改 n1/n2，强写还可改 n3，n4～n6 不在写范围。写工具只修改本次进程的内存值；实验应用仍仅注册统计工具，其配置的写连接为空。

```powershell
python -m scripts.run_network_agent "从 root 弱写把 n2 的 value 更新为 42，随后读取核对。"
```

真实 API 测试已实际调用 describe_node、weak_write、weak_read，n2 更新为 42，写路径为 root→n1→n2，写后读取核对成功；其他数字未改变，CSV/SQLite 实验数据未修改。

读取工具的 node_id 参数可选，不提供时从 Agent 所属的 root 出发，显式提供时仍可选择其他已注册节点。数字演示新增 root→n1 强读连接；默认弱读为 [1, 2, 4]，默认强读为 [1, 2, 3, 4, 5, 6]，来源路径从 root 开始。底层 Network 的起点参数保持显式。


## 按需发现子节点工具

工具按职责放置：ValueNode 的 get_value、CSV 的 get_record/query_records、SQLite 的 get_record 位于各自节点；合格率 analyze_project 仍位于组合输入的根节点。节点工具通过 register_tool 显式登记用途、参数和 read_only；直接写入 tools 字典但未登记的工具不会跨节点公开。

根 Agent 初始定义保留常用根工具，加上 list_nodes/list_tools/invoke_tool 三个通用入口，不预加载全部子节点工具参数。

```python
root.invoke_tool("list_nodes")
root.invoke_tool("list_tools", target_node_id="n2")
result = root.invoke_tool("invoke_tool", target_node_id="n2",
                          tool_name="get_value", arguments={})
```

发现与调用固定从 Agent 所属节点出发，scope 默认 integrated，可选 local/federated；使用 BFS 读取范围，支持环和重复节点。节点目录返回概况和只读工具数量，list_tools 才返回完整用途、参数与所属节点。调用时使用节点 ID 与工具名区分同名工具，返回执行结果和工具访问路径，不启动目标 Agent，不给目标工具额外注入根上下文。

模型入口必须先 list_tools 发现具体工具；执行前重新检查范围、只读声明和参数。写工具及未声明工具不能经读连接调用。当前参数检查支持 JSON Schema 的类型、字段、必填、额外字段、枚举和数组项目子集，不是完整 JSON Schema 验证器。read_only 是开发者的显式声明，不是隔离恶意代码的沙箱；应用必须保证声明真实。工具函数和动态工具定义不直接写入网络配置；可保存工具定义文件路径，加载后重新装配。

真实 API 已按 list_nodes → list_tools → invoke_tool 执行，发现 n2 的 get_value 并取得 2；子节点无 Agent，数据未修改。


## 提示词文件与 Agent 实例重启

Agent 改为接收 prompt_path，创建时以 UTF-8 读取文件，保存正文为 system_prompt。文件缺失、编码错误或内容为空时初始化失败。不同节点可指定不同职责文档，不在 Node 上重复保存提示词。

```python
from datanet.agent import Agent

node.agent = Agent(client=client, model=model,
                   prompt_path="prompts/child.md", tool_definitions=definitions)
# 编辑绑定的提示词文件后重新加载，清空旧会话
node.restart_agent()
```

重启先等待当前任务结束，再以原客户端、模型和工具定义创建新实例，成功后替换 node.agent；失败保留旧实例和会话。节点的数据、连接和工具不变。客户端由应用管理，不会在重启时关闭。Agent 不允许在自身正在执行的任务中同步重启自己，避免死锁。reset() 只清空内存历史，不重新读文件；外部编辑文件需要重启才生效。

此阶段只提供 Python restart_agent 管理接口，尚未向模型开放提示词文件编辑或跨节点重启工具，也没有新增管理权限机制；未来开放时需单独授权，不复用业务数据写权限。Agent 提示词路径和创建参数现在保存在网络 JSON v2，客户端由应用提供。


## 配置驱动的多 Agent 网络与任务委托

JSON v2 每个节点增加 agent 配置（无 Agent 为 null），网络顶层增加 delegations。提示词和工具定义文件的相对路径以网络 JSON 所在目录为基准。

```json
{
  "model": "deepseek-chat",
  "prompt_path": "prompts/worker.md",
  "tools_path": null,
  "max_rounds": 8,
  "max_tokens": 1000,
  "thinking": false
}
```

上述对象是节点的 agent 字段。tools_path 为 null 时从已注册的本地只读工具元数据生成定义，否则读取指定 JSON 文件；装配器额外添加发现与委托入口。thinking 为 null 时不发送思考开关。密钥及任意 extra_body 不保存。加载配置不会创建客户端或请求模型；应用装配本地/组合工具后执行 `assemble_agents(network, client, model_override=...)`，模型覆盖值可由 .env 提供。全部新实例构建成功后才绑定到节点；旧 v1 网络仍可加载，但没有 Agent 配置与委托许可。

```json
"delegations": [{"source": "root", "target": "worker"}]
```

委托许可是单独的直接有向授权，不由读写权限推导、不沿许可链传递。ask_agent 固定从所属节点出发，目标必须获得该许可、在指定读取范围可达并已配置 Agent。

```python
root.invoke_tool("ask_agent", target_node_id="worker", message="读取你的本地数字")
```

目标使用自己的已加载系统提示词、工具和访问范围，本次任务从独立的系统/用户消息开始，不读取或改写目标既有历史。任务内容仅为用户输入，不替换系统提示词。ask_agent 可能间接使用目标写工具，因此不标记为只读，也不经只读工具发现公开。

调用链拒绝重复进入同一节点；固定上限为链中 4 个 Agent、每个根任务 8 次委托，子任务共享次数预算。同步委托遇到目标忙碌时立即报错，不等待它的锁，避免多条并发调用链互相等待。模型失败通过委托结果报告，已执行的写操作不会回滚。当前是同进程同步请求/回复，没有消息队列或跨进程认证，也没有整个任务的总时限；单次 API 超时由客户端设置。

```powershell
python -m scripts.run_multi_agent "请委托 worker 读取它的数字，再告诉我结果"
```

applications/multi_agent/network.json 保存 root 和 worker 的不同提示词、模型参数、读连接与许可，数字为模拟内存值 42。实验和数字应用也改为从各自网络 JSON 装配 Agent。真实 API 已执行 root→ask_agent→worker.get_value→回复 42，子历史未混入任务，模拟数据未修改。


## 节点用途与动态数据结构

Node 增加可选 description 字符串，用于说明节点职责和数据范围，保存到 network.json；旧 v1/v2 配置省略该字段时默认为空字符串。data_kind 仍表示数据类别，不被描述替代。

```python
node.description
node.schema              # 只读动态属性，等价于 get_schema()
node.get_schema()
node.describe()          # 包含 description 和 schema
```

schema 不保存为第二份配置，避免过期。基础 Node 返回 None；ValueNode 描述固定键 value 和当前值类型，不暴露值；CSV 只读取表头，字段类型来自已配置 dtype，未配置时明确为未知，不猜测整列类型；SQLite 只读查询实际表结构，返回列声明类型、NOT NULL、主键顺序与默认值。SQLite 声明类型不代表额外实施严格类型检查，schema 也不新增写入校验规则。

节点目录 list_nodes 仅返回概况和 description，不自动加载全部 schema；查看具体节点或调用本地只读工具 get_schema 才按需获取结构。存储缺失或结构错误时 describe 返回 schema=null 和 schema_error，get_schema 工具返回错误结果，不静默当成无结构，也不创建文件。动态结构可能发生变化，执行查询/写入时仍由后端检查。
