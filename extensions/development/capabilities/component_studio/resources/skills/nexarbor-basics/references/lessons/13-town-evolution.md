# 小镇案例分析

以下优化建议来自标准正面示范：

1. 多利用信号“广度逐层推进、同层并行”的机制安排并行，而不是把独立任务串起来。样板中的 NPC 就在同一层并行活动。接线见 `nodes/0b4a4274c354d8b6.json`，活动模块见 `modules/agents.activity/module.py`。
2. 不把很多功能耦合进一个模块。即使是很专用的模块，相互独立的机制也要分开制作。
3. 修改网络时严格注意操作顺序，避免执行到一半丢失后续操作路径，像用指针操作单链表一样谨慎。样板的移动模块先接新地点、更新信息，再断旧连接：`modules/movement.here/module.py`。
4. 能用已有模块组合实现，不等于应该强行复用。例如用可配置业务服务逐条配置出售、回收物品，虽然能工作，却不符合商店以商品表管理售价和回收价的逻辑；这时应建立职责明确的新模块。对照 `modules/service.actions/module.py` 与 `modules/shop.market/module.py`。
5. 不为复用而硬把两个功能做到一起。模块最重要的是功能单元化；制作复杂模块时，先想它能否拆成两个更简单的模块。

完整标准样板：`<安装目录>/resources/examples/npc-town/`。这是安装包自带的完整项目，安装目录由本会话的宿主指令给出；上述路径均相对样板目录。

按需加载 `inspect-network`，用 `view_network(project="样板文件夹的绝对路径")` 查看。之后可用同一套工具筛选网络、查看节点与模块，按行读取源码和文本，无需启动样板。也可以把 `project` 换成任意其他 Nexarbor 项目文件夹。

项目入口为 `nexarbor.json`，活动网络清单为 `networks/main.json`。出生模板在该文件的 `runtime.templates`，ID为 `newborn-a`、`newborn-b`，不是独立的 `templates.json`。

- 四路上下文：`modules/context.assembler/module.py`；工具收集：`modules/tools.collector/module.py`。二者直接使用 BFS 节点对象表，避免逐节点再寻路。
- 居民装配示例“小砾”：`nodes/5dc2deba4ffb98f1.json`；工具亚节点：`nodes/1898820b5c48059f.json`。新样板把上下文组装器直接装在居民上，工具亚节点独立放工具收集器。
- 原始计数“世界时钟”：`nodes/9c5cd5fa03c13390.json`；可读时间与并行分叉“世界时间”：`nodes/0b4a4274c354d8b6.json`；存档点：`nodes/f3c0824822d7578a.json`。

源码用 `read_resource(module="movement.here", file="module.py")`；网络及模板用 `read_network_text(file="networks/main.json")`，节点用上述真实文件名。逻辑文本路径与实际正文文件的映射也在网络清单中，不按节点ID猜文件名。同一轮后续查看沿用已选项目；用 `source="current"` 或 `source="candidate"` 切回当前工作流。

样板含59个初始节点、19个项目模块。以本项目的 `nexarbor.json` 中 `resources.modules` 为准读取实现，不去核心组件目录猜路径；组件名称相同也不保证当前项目的版本、配置相同。
