# LabInsight Agent

基于模拟实验数据的分析助手。用户用自然语言指定项目，模型通过工具调用获取本地统计结果，再生成中文分析报告。

当前是学习与开发中的原型；实验记录为随机生成的模拟数据，不代表真实实验结果。

## 当前功能

- 使用 NumPy、pandas 生成实验记录，支持模拟缺失值。
- 按项目筛选有效记录，计算有效数、通过数、失败数和合格率。
- 使用 SQLite 保存项目判定规则，并生成对应的判定函数。
- 通过 DeepSeek 的兼容接口实现工具调用和多轮结果反馈。
- 将提示词、工具定义和路径配置独立保存。

有效记录要求：属于指定项目、`是否有效` 为“是”、`测量值` 不缺失。合格率为通过数除以有效数；没有有效记录时返回 `null`，而不是 0。

初始化规则：A 的测量值至少为 80；B 在 40～60 之间（包含两端）；C 至多为 20。默认生成范围为 50～100，因此 C 项目默认没有合格样本。

## 目录结构

```text
labinsight/
  analysis.py             # 纯统计逻辑
  rules.py                # SQLite 规则查询、判定函数
  tools.py                # 工具包装与注册表
  agent.py                # 模型请求与工具调用循环
scripts/
  generate_data.py        # 生成模拟数据
  init_db.py              # 初始化规则数据库
  run_agent.py            # 命令行入口
agents/
  prompts/report_system.md
  tools/tools.json
data/
  实验记录01/01.csv
  lab.db
notebooks/                # 学习和探索用 notebook
config.py                 # 统一路径配置
```

## 环境准备

使用 Python 3.11 或以上版本，在已激活的 Python 环境中安装依赖：

```powershell
python -m pip install numpy pandas openai python-dotenv
```

在项目根目录创建 `.env` 文件：

```dotenv
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_MODEL=你的账户支持的模型名称
```

模型需支持工具调用及当前使用的关闭思考配置。`.env` 已加入 Git 忽略规则，请勿上传密钥。

## 运行

以下命令均在项目根目录执行。

### 初始化数据和规则

仓库提供模拟 CSV。需要重新生成时执行下列命令，注意它会覆盖当前模拟记录：

```powershell
python -m scripts.generate_data
```

初始化 SQLite 规则表：

```powershell
python -m scripts.init_db
```

重复初始化会保留已有项目规则；修改初始化脚本不会自动更新数据库中的已有规则。

### 调用助手

```powershell
python -m scripts.run_agent "请查询项目 B 的合格率。"
```

不传问题时使用默认的 B 项目查询：

```powershell
python -m scripts.run_agent
```

### 仅运行本地统计

不需要 API 密钥，也不会请求模型：

```powershell
python -c "from labinsight.tools import analyze_project_tool; print(analyze_project_tool('A'))"
```

## 工作流程

1. 加载系统提示词和工具定义，将用户问题发送给模型。
2. 模型提出工具名和项目编号。
3. 本地程序通过注册表找到函数，查询规则数据库并读取 CSV。
4. Python 计算统计指标，将结果返回给模型。
5. 模型根据工具结果生成报告；最多请求 5 轮。

模型不会直接执行任意 Python 代码，也不会接收完整 CSV。判定阈值来自本地规则数据库。

## 当前边界与后续计划

目前支持单份 CSV、基础阈值规则和命令行交互。工具调用使用 `auto`，模型可能选择直接回复。尚未实现文档检索、RAG、可视化界面和系统化评估。

后续计划：在结果中增加规则与数据来源，加入实验规范文档查询，并评估回答的准确性与可追溯性。
