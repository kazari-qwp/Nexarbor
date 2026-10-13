# 固定五人讨论小组

`package.json`是网络预设：Leader、Recorder和三名普通成员，共14个节点。
不包含协调Agent，也不提供按人数生成的功能。

- `board`：讨论黑板与`run_discussion`调度工具；成员只能追加发言，读取上轮快照。
- `project`：项目目标、进度和当前工作，成员只读。
- `notebook`、`output`：公共笔记和成果，只有Recorder拥有写入接口。
- 每人一个私人笔记；其他成员没有读写路线。

读写接口、可见性和黑板到五人的委托许可都在网络JSON中。
成员通过自己的private接口访问黑板，再沿public读接口访问共享文档。
黑板到成员的接口为private，外部调用者不能穿透黑板访问成员。
成员信号上限为2；调用黑板建议提供强度2，外部根节点经一跳调用则提供3。

外部根节点应分别连接三个导出入口：`board`读写、`project`读写、`output`只读。
根节点先写项目说明，再调用黑板的`run_discussion(task, rounds=8)`。
默认八轮共40次成员调用，最后1次Recorder收尾；全请求委托上限为64。
黑板读取内容顶部显示“当前轮数：0/8”，每轮开始更新为1/8至8/8；下方仍展示上一轮发言。
成员会话保留；每轮归档并清空追加区由代码完成。

```python
from datanet.components.networks.discussion_group.setup import build_discussion_group
from datanet.core.agent_configuration import assemble_agents

network, mounted = build_discussion_group("team_a")
network.nodes[mounted.entry_points["project"]].write("content", "项目目标：……")
assemble_agents(network, client)
board = network.nodes[mounted.entry_points["board"]]
result = board.run_discussion("讨论并给出实施方案", rounds=8, strength=2)
```

加载或挂载预设必须登记`setup.TOOLKITS`；它按实例节点ID为文档分配独立运行目录。
默认数据保存在`.models/runtime/discussion_groups/`，不会写进组件模板目录。
相同实例ID重新加载会继续使用已有文档；不同实例ID数据隔离。
组装配置不请求模型；真正运行讨论才会调用API。

每名成员每轮最多10次模型请求，程序提示“当前请求次数：?/10”。成员自主读写笔记，使用submit_round提交发言或skip_round跳过，成功后直接结束本轮。未在额度内完成选择会报错并保留本轮记录，不能把未提交正文当作发言。

## 最小真实API验证

在项目根目录运行`python -m datanet.components.networks.discussion_group.validate_api`。
读取项目.env中的DeepSeek配置，根Agent通过create_network一次创建五名Agent，调用黑板工具讨论两轮。
每人每轮提交精确文本“测试”，Recorder最后写入并返回“成功”。测试会真实调用API。
报告与模型/工具轨迹保存在`.models/research/discussion_validation/<运行编号>/report.json`，不保存API Key。
2026-10-10验证通过：两份归档各有五条“测试”，Recorder成果及回复均为“成功”；该成功运行共18次模型请求。
