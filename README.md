# Data Node with Agent

[GitHub 仓库](https://github.com/kazari-qwp/data_node_with_agent)

可组合的 Agent 数据网络。节点提供数据和工具，通过不同的读取、写入连接组成有向网络；需要推理的节点可以配置独立 Agent。Python 框架包名保留为 `datanet`。

目前已实现只读网络和实验分析演示：根 Agent 调用根节点的合格率工具，工具经网络读取 CSV 实验记录和 SQLite 判定规则，再用 Python 计算并返回来源。实验记录全部为模拟数据。

## 已实现的能力

- 基础 `Node`、统一结果 `NodeResult` 和本地工具箱。
- 通用 `CsvNode`、`SqliteNode` 和内存单值 `ValueNode`。
- 节点共享地址接口，分别保存强读、弱读、强写、弱写连接。
- BFS 读取、环与重复节点去重、数据类型筛选和来源路径。
- JSON 网络配置保存与加载，恢复节点参数和四种连接。
- CSV 主键读取、多个等值条件查询；SQLite 只读主键查询。
- 节点默认 agent=None；绑定实例即可调用，设回 None 即移除，可保留或重置实例的会话历史。
- 模型工具调用通过所在节点的工具箱执行，不依赖全局业务注册表。
- 实验应用的模拟生成、规则初始化、网络统计与中文报告。
- 数字网络 Agent 演示：查看节点连接，从指定节点执行强读、弱读。

写连接列表和写入入口已预留，实际写入尚未实现。RAG、动态记忆整理、NPC 消息传播和自主创建节点都是后续目标，不属于当前成果。

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

JSON v1 支持基础、单值、CSV、SQLite 四种节点，保留节点顺序和四种连接列表，支持环和同一地址出现在多个列表。相对数据路径以配置文件所在目录为基准；跨盘符时保存绝对路径。加载不会打开或创建实际数据文件。

CSV、SQLite 只保存访问参数和路径，数据继续保留在原文件；单值节点保存 JSON 原生值。自定义节点类型、非 JSON 单值和非字符串 CSV dtype 明确报错。未知版本、重复节点、缺失连接目标或多余字段也会报错。保存使用临时文件替换，校验失败不会覆盖已有配置。

工具、Agent、密钥及会话历史不写入配置，加载后的节点 `agent=None`、工具箱为空，由应用重新装配。实验应用的三节点结构已迁移到 `applications/experiment/network.json`，Python 装配层只加载配置并绑定合格率工具，不再硬编码节点和连接。

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

根节点注册 `describe_node(node_id)`、`weak_read(node_id, key)`、`strong_read(node_id, key)`。数字节点 n1～n6 的查询键为 `value`。从 n1 弱读得到 `[1, 2, 4]`，强读得到 `[1, 2, 3, 4, 5, 6]`，结果包含来源及首次发现路径；环与重复连接不会导致重复读取。可以把起点改成 n3 或 n5。

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

当前 75 项本地测试覆盖存储读取、条件查询、强弱范围、写连接隔离、环去重、缺失输入、网络统计、配置保存加载和模拟 Agent 调用。测试使用独立临时文件；模型响应由模拟客户端提供，不消耗 API 额度。这些是功能测试，不代表已有独立检索性能评估。

数字网络的真实 API 验证中，模型实际调用了节点描述、弱读和强读三个工具；工具反馈中的数字序列已与本地遍历结果核对。

2026-10-09 的真实 API 验证中，模型实际调用一次根统计工具，经网络取得 B 项目有效 18、通过 9、失败 9、合格率 50%。这是模拟数据快照的结果，不是固定业务结论。

完整目标见 [项目目标](docs/PROJECT_GOALS.md)，实际阶段记录见 [项目进度](docs/PROJECT_PROGRESS.md)。后续包括精确事实版本、任务恢复、RAG、基于使用反馈的记忆关联与冷热分层，以及 NPC 分圈消息传播；Agent 自主创建节点安排在最后。
