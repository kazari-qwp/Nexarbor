# 织林 · Nexarbor

把 Agent、数据、工具和模块放到同一张画布，用连接、频道和强度组装应用；也可以在节点或网络上咨询制作 Agent，在工作副本中制作、验证和发布组件。

本目录是基于模块化核心的迁移工程。三个应用、约定前端功能与六份演示已完成迁移验收；小镇还从前端追加运行第六天概率事件。交付与实测范围见 [交付说明](docs/migration/DELIVERY.md)。

## 从源码打开

运行环境为 Windows x64、Python、Node.js、Git 和 DeepSeek Harness。模型连接在客户端本机配置，不将密钥写进项目。

```powershell
python -m venv .venv-runtime
.\.venv-runtime\Scripts\python.exe -m pip install -r requirements.txt
npm install
npm --prefix frontends/network-editor install
npm --prefix frontends/desktop install
npm run build
npm start -- --project "E:\项目_手动重构\项目演示\应用3-NPC小镇-初始"
```

也可以先运行 `npm start`，在首页打开项目文件夹。每份演示目录提供 `打开项目.cmd`；在当前源码目录中使用。Harness 路径、模型连接和可选的本地向量模型在设置或应用配置中指定。普通会话、制作会话与内部摘要默认显式使用 high，请求上限为 10000。

## 六份演示

| 应用 | 初始状态 | 测试后状态 |
| --- | --- | --- |
| 讨论与协作 | [初始项目](项目演示/应用1-讨论协作-初始) | [最终项目](项目演示/应用1-讨论协作-最终) |
| 知识资料库 | [初始项目](项目演示/应用2-资料库-初始) | [最终项目](项目演示/应用2-资料库-最终) |
| NPC 小镇 | [初始项目](项目演示/应用3-NPC小镇-初始) | [最终项目](项目演示/应用3-NPC小镇-最终) |

最终状态来自实际运行：应用一由管理员组装讨论和协作网络，完成 CSV 转 JSON 项目；应用二保留原文、集合、版本、索引和导航；小镇运行五天、25个时刻。双击 Agent 可查看保存的原生会话历史。不要在原始交付目录中做破坏性试验，先复制项目。

对应验收、时间和 token 统计分别见 [讨论协作](docs/migration/HONE_RESULT.md)、[资料库](docs/migration/KNOWLEDGE_RESULT.md)、[五天小镇](docs/migration/TOWN_FIVE_DAY_RESULT.md)。

## 结构与操作

节点持有模块表、工具箱和出边，模块提供业务能力。连接表达访问范围，频道、阈值、倍率、节点偏置和汇合策略决定一次访问能到哪里。异步访问按广度分层、同层并发；模块通过 `@access` 对取得的单个节点执行操作。普通节点不承担模型或数据存储职责，数据节点继承 `DataNode`，Agent 是独立节点类型。

前端模块亚节点只是比普通节点小的名称矩形，不增加运行节点或访问权限。频道保留在声明、配置和悬停提示中。节点、边、模块、工具、Skill 与网络可以复制到书签或保存成磁盘资源；复制保留已有表，不补装或检查依赖。装配新能力才使用安装器的依赖处理。

项目采用真实文件、Git 和 DSH 日志持久化。节点锁与局部事务负责并发及回滚；DSH 保管模型会话，适配层负责工具、输入、上下文和会话位置。网络制作和组件制作 Agent 保留原工具工作流，详细 Skill 按需读取。

目录、调用链和建议阅读顺序见 [项目结构与机制说明](PROJECT_OVERVIEW.md)。前端实测范围见 [验收清单](docs/migration/FRONTEND_ACCEPTANCE.md)。

## 本地回归

```powershell
.\.venv-runtime\Scripts\python.exe -B -m unittest discover -s tests
npm run test:frontend
npm run test:desktop
```

这些命令运行本地回归。真实模型测试单独授权与统计，不由普通回归命令启动。`build/` 保存本机测试截图、日志和临时项目，不作为产品源码。可选向量能力需要应用声明的依赖与本地模型权重。
