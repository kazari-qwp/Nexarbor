# 正式开工：第一版节点

日期：2026-10-09。对应目标阶段 1；目前不需要 API、RAG 或模型。

本文保留第一版开发过程。当前节点已迁移到同名子包，RuleNode 已替换为 SqliteNode，labinsight 已拆除；实际目录、导入和当前运行方式以 [README](../README.md) 为准。

## 1. 先运行

在 VS Code 终端进入项目根目录，使用已装依赖的 ml 环境：

```powershell
conda activate ml
cd E:\数据库项目
python -m scripts.demo_nodes A
```

输出是一个 JSON 对象，含两种节点的描述与查询结果。关键内容：rule_result.status 为 ok，items 中规则为 A 至少 80；sources 中是 data/lab.db 的 rules 表。composite_local_result.status 为 not_found，items 为空，因为 root 暂无本地数据，也还没有接口。

更换查询主键：

```powershell
python -m scripts.demo_nodes B
python -m scripts.demo_nodes Z
```

B 返回 40～60 区间；当前数据库没有 Z 时返回 not_found。查询不写入数据库、不改变实验 CSV。

## 2. 三个对象分别是什么

- Node：约定所有节点拥有 node_id、name、data_kind，并通过 describe/get 提供统一入口。它是抽象基类，不能直接当具体数据库使用。
- RuleNode：Node 的一种具体实现。只保存/访问实验规则这一类数据，用 SQLite 后端按项目主键读取。构造对象不会复制数据库。
- CompositeNode：没有本地数据的入口节点。以后网络层负责组合它的连接；这一步先明确本体没有数据。

先从 labinsight/nodes.py 的 RuleNode.get 阅读，再回到 memorynet/nodes.py 看共同结构。已有 labinsight/rules.py、tools.py 和模型循环保持原接口可用，不需要先把所有代码重写。

## 3. 不经过 CLI 的直接调用

下面可以放入项目根目录的探索脚本，或在 Python 交互模式使用：

```python
from labinsight.nodes import RuleNode

node = RuleNode()
result = node.get("A")

print(node.describe())
print(result.status)
if result.status == "ok":
    print(result.items[0]["content"])
    print(result.sources)
```

get 的参数是业务主键，这个节点的业务主键就是 project_id。NodeResult 是统一结果对象；to_dict 把它转成普通字典，供 JSON 序列化或未来工具返回使用。

status 区分四种情况：ok 查询成功并返回内容；not_found 没有这个主键；unsupported 这个操作尚不支持；error 后端读取失败。缺失数据库与缺失记录不同：前者报 error，而且只读连接不会意外创建空数据库。

items 保存内容和归属身份；sources 保存实际来源；truncated 以后用于表示预算截断；request_id 当前标识一次本地调用，网络阶段将由入口产生并传递同一个请求 ID。version 为 null 是因为现有表没有版本，不表示已经实现历史规则。

## 4. 本地检查

```powershell
python -m unittest discover -s tests -v
```

测试用独立临时 SQLite 文件，不修改 data/lab.db；无需安装新的测试库。

## 5. 下一步只做一件事

增加“实验记录节点”，按记录编号 get、按项目 query；完成后再让组合入口通过有向强接口访问规则和记录。动态关联、遗忘、NPC 传播和自主建库已写入目标，当前先做好它们共用的节点与权限基础。
