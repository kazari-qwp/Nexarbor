# Data Node with Agent

[GitHub 仓库](https://github.com/kazari-qwp/data_node_with_agent)

可组合的 Agent 数据网络。节点提供数据和工具，通过不同的读取、写入连接组成有向网络；需要推理的节点可以配置独立 Agent。Python 框架包名保留为 `datanet`。

目前已实现只读网络和实验分析演示：根 Agent 调用根节点的合格率工具，工具经网络读取 CSV 实验记录和 SQLite 判定规则，再用 Python 计算并返回来源。实验记录全部为模拟数据。

## 已实现的能力

- 基础 `Node`、统一结果 `NodeResult` 和本地工具箱。
- 通用 `CsvNode`、`SqliteNode` 和内存单值 `ValueNode`。
- 节点共享地址接口，分别保存强读、弱读、强写、弱写连接。
- BFS 读取、环与重复节点去重、数据类型筛选和来源路径。
- CSV 主键读取、多个等值条件查询；SQLite 只读主键查询。
- Agent 默认关闭，可绑定独立实例、切换开关、保留或重置会话历史。
- 模型工具调用通过所在节点的工具箱执行，不依赖全局业务注册表。
- 实验应用的模拟生成、规则初始化、网络统计与中文报告。

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
  nodes/
    node/node.py                 # 基础节点、结果与工具箱
    csv_node/csv_node.py
    sqlite_node/sqlite_node.py
    value_node/
      value_node.py
      demo.py
      demo_network.py            # 数字网络与强弱读演示
applications/
  experiment/                    # 完整实验应用
    network_setup.py             # 组装节点、连接及根工具
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

根节点绑定并开启 Agent，规则和记录节点默认关闭。每次任务最多请求 5 轮；模型返回工具请求后，根节点执行网络统计工具并回传结果。工具选择为 `auto`，模型也可能直接回答，当前尚未强制所有统计回答都有成功的工具证据。

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

当前 59 项本地测试覆盖存储读取、条件查询、强弱范围、写连接隔离、环去重、缺失输入、网络统计和模拟 Agent 调用。测试使用独立临时文件；模型响应由模拟客户端提供，不消耗 API 额度。这些是功能测试，不代表已有独立检索性能评估。

2026-10-09 的真实 API 验证中，模型实际调用一次根统计工具，经网络取得 B 项目有效 18、通过 9、失败 9、合格率 50%。这是模拟数据快照的结果，不是固定业务结论。

完整目标见 [项目目标](docs/PROJECT_GOALS.md)，实际阶段记录见 [项目进度](docs/PROJECT_PROGRESS.md)。后续包括精确事实版本、任务恢复、RAG、基于使用反馈的记忆关联与冷热分层，以及 NPC 分圈消息传播；Agent 自主创建节点安排在最后。
