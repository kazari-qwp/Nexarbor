# NPC 小镇标准样板（初始状态）

这是本轮交付的小镇初始项目，作为普通 Nexarbor 项目随安装包提供。包含59个初始节点、19个项目模块、上下文文本、工具声明和两个新生儿模板，不包含五天实测终态、旧会话或测试日志。

完整目录：`<安装目录>/resources/examples/npc-town/`。应用模块的源码以本项目的`nexarbor.json`资源声明为准，不要求核心组件目录内存在同名模块。运行或修改时先复制整个目录，再从客户端打开项目文件夹；客户端会建立本项目的Git和启动入口。

Agent先加载`inspect-network`，调用`view_network(project="本目录的绝对路径")`。后续查看沿用该项目；用`read_resource`按需读模块，用`read_network_text`读项目清单和节点JSON；切回当前工作流使用`source="current"`或`source="candidate"`。

| 入口 | 项目内实际路径 |
|---|---|
| 项目清单与模块地址 | `nexarbor.json` |
| 完整网络、出生模板 | `networks/main.json`，模板在`runtime.templates`，ID为`newborn-a`、`newborn-b` |
| 脉冲“每刻” | `nodes/c41be5112d950adf.json` |
| 原始时钟计数“世界时钟” | `nodes/9c5cd5fa03c13390.json` |
| 可读时间与NPC并行分叉“世界时间” | `nodes/0b4a4274c354d8b6.json` |
| 居民“小砾”的装配、上下文与工具来源 | `nodes/5dc2deba4ffb98f1.json` |
| 小砾工具亚节点 | `nodes/1898820b5c48059f.json` |
| 存档点 | `nodes/f3c0824822d7578a.json` |
| 医院 | `nodes/1f6835c0d878fa0e.json` |

| 学习内容 | 源码 |
|---|---|
| 收到信号后运行角色 | `modules/agents.activity/module.py` |
| 节点对象访问、短事务与移动顺序 | `modules/movement.here/module.py` |
| 四路上下文、BFS顺序与串联 | `modules/context.assembler/module.py` |
| 节点工具表直接收集与串联 | `modules/tools.collector/module.py` |
| 可配置业务与商品表商店的区别 | `modules/service.actions/module.py`、`modules/shop.market/module.py` |
| 双人同意、怀孕与生产的职责拆分 | `modules/agreements.pair/module.py`、`modules/family.household/module.py`、`modules/family.birth/module.py` |
| 可读时间与定期存档 | `modules/world.time/module.py`、`modules/runtime.periodic_checkpoint/module.py` |

居民的上下文组装器装在居民本节点；需要独立工具检索出边的工具收集器放在亚节点。只在需要独立出边时使用亚节点，不强制每个模块建立一个亚节点。

文本的逻辑路径由网络清单`files`映射到`network-resources/`中的实际正文文件；还有`data/`、`context/`中的项目文本。按清单查找，不能根据节点ID拼接文件名。本项目没有独立的`templates.json`；出生模板直接读`networks/main.json`的`runtime.templates`。
