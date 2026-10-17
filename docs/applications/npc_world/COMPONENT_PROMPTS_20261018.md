# 组件制作提示与反馈原文（2026-10-18）

这些是组件工作副本的实际输入。详细输入先行；同前缀的修正沿原会话继续或分叉。部分会话自行查看过旧实现，因此不把任何一个例子标为隔离源码盲测。

## budget-task.json

会话：`session-51b1add7-0e69-4af2-a7b1-62a9c77c2309`

```text
做一个通用行动值组件，挂在Agent上。每个新时刻恢复到配置的上限，默认10；别的组件可以先检查剩余，再扣除指定消耗，余额不够就明确拒绝且不扣。重复同一个时刻不重置。提供查看余额、检查、扣除的内部操作，提示里要能知道还剩多少。不要写移动或挖矿业务。
```

## clock-task.json

会话：`session-e56faa13-88a4-4956-9734-1a21da944ddc`

```text
做一个通用的时间文本组件：每收到一个新脉冲，时间往前走一格，重复的同一信号不重复走。一天早上、中午、下午、傍晚、午夜五格，天数和文字都能配置；把时间写到挂载的文本节点。别做整个世界。提供读取当前天数和总时刻的内部操作，重启之后接着走。
```

## entity-task.json

会话：`session-25fa8ae8-3fdc-4e4f-9dd3-63de4059ae3f`

```text
做一个通用实体资料和物品组件，挂在任何节点上：配置初始资料、金币和物品，状态持久化。其他组件能读取资料，更新字段，原子地增减金币和物品；余额和数量不能为负，失败不能改一半。资料还能通过核心统一元数据接口看到。不要做商店、职业、移动之类业务，也不要公开让Agent任意改自己物品的工具。
```

## family-fixed/family-presence-fix-task.json

会话：`session-0b51a859-1923-4b9e-b38a-6755019f0cb9`

```text
集成验收发现plan_child只检查双方profile.place，没有检查双方profile.home确实等于此处；civil/family/hospital也不能只信profile.place，必须核实人物与配置place有匹配presence_channel的真实双向在场连接。请补齐：family要求双方home==place，civil和family检查双方在场，hospital检查产妇在场；拒绝不扣费，不修改同意或资料。presence_channel可以给全部mode配置，示例和说明同步更新；保持现有公开字段和正常流程，版本1.0.1。孩子管理归属可以增加child_template.management_parent_id配置，创建时按该配置设置，避免无主节点。补针对伪造位置、去别人家、缺失反向连接的测试。不写兼容代码，不运行命令。
```

## phase2/activity-task.json

会话：`session-8aef108b-295c-400f-9eba-626637c9d961`

```text
做一个通用的Agent活动组件，挂在Agent上，收到world.tick后调用并等待框架原生Agent执行端口：await backend.execute_agent(self.node.node_id,message=配置的提示语)。组件自己不要实现模型循环、工具装配或NPC逻辑，也不要用submit工具。没有工具调用正常结束就算完成；记录成功处理的signal_id，同一信号不重复执行，失败不能登记成功。setup只初始化本地状态；需要async on_signal，异常交给框架。只做这个组件，示例不要接整张网络。
```

## phase2/clock-first-tick-task.json

会话：`session-5d9b4b13-d79c-4439-979c-a68fec8ef0b1`

```text
装配测试发现：现在第一个脉冲会变成中午。请改为尚未开始tick=-1，第一个新脉冲才进入第1天早上（tick=0），第五个是午夜，第六个是第2天早上。同步更新schema、文档和测试，版本改1.0.1，保留现有其它行为。不要写兼容分支，也不要运行命令。
```

## phase2/context-task.json

会话：`session-5cd5f4e3-5b74-4064-b790-fcd0a1f7ce0d`

```text
做一个通用的居民上下文准备组件，只提供内部prepare操作，不启动Agent。依赖文档在dependencies。配置给出本节点实体/行动值组件ID、时钟节点/组件ID、人格文件、常识文件、地图文件和一次性开场白。prepare把人格和常识作为system_prompt、地图作为保证存在的context、开场白作为只投递一次的inputs，当前时间/自身资料物品金币/行动余额/本地场所与同场人物/相邻地点名称作为每次重算的tail。资料采用entity.profile的profile.place标示当前地点；地点道路和在场连接使用配置的频道，仅依据真实当前连接，不取远处人物和物品，不遍历world.tick。其它人物只公开姓名性别职业。文件是backend.directory下的相对路径，每次prepare可以重新读文件；读不到明确报错。首次标记在state中保存，读档不重发开场白。宿主会在每次模型请求前调用prepare，因此移动和别人来去后现场信息会更新。不要写移动或启动模型的代码。
```

## phase2/movement-task.json

会话：`session-74fe3aee-4670-4123-a5ec-3cdbfbf7f140`

```text
做一个通用地点移动组件，挂在地址节点，公开一个不填参数的move_here工具。工具描述显示本地点名称和移动花费，频道由配置给出。身份用current_agent_id()，不是模型参数。人物位置读entity.profile的profile.place；只允许从真实当前地点走到与本地点直接相邻且指定道路频道相通的地点，自己位置不动不扣费，配置行动值组件ID和默认消耗3，余额不足不移动。成功后迁移人物与旧、新地点的双向在场连接，只移除在场频道，不破坏脉冲等其他频道；节点与道路都保持散度-1、门槛1。更新人物profile.place，返回地点名称、剩余行动值和简明到达信息，移动后仍允许继续行动，不结束Agent。人物状态和扣费用核心模块事务保证失败不扣，不写旧接口兼容。不要实现其他场所业务或整张地图。
```

## phase2/social-task.json

会话：`session-a584ff1e-12e7-41bc-a3da-8166633a9cd7`

```text
做一个通用同场所交流组件，挂在每个Agent上，对外公开talk工具，参数只有message。可信调用者用current_agent_id，要求双方profile.place相同且真实在场；对方已离开时返回“他好像已经去了某地点，已经不在这里了”，不要自动追过去。频道配置为同场交互频道。说话扣发送者1行动值（配置可改），不足不发送。把带发送者姓名和唯一ID的信息写进接收者Agent.inputs的inputs通道，由框架在其下次模型请求时处理，不要自动启动对方，不要自动回复，避免无限互相唤醒。返回发送成功和剩余行动值。依赖通过配置的组件ID调用，公开描述要以收话者姓名呈现。
```

## phase3/events-task.json

会话：`session-83258206-9baa-4c21-bdc7-05965af3edd5`

```text
做一个通用概率信息组件，不公开Agent工具，只提供draw内部操作。配置是一组事件：id、触发动作列表、独立固定概率、最多命中次数（null为无限）、文字message、可选effects原样返回。draw接收trigger和context字典，分别独立抽每个适用事件，不能把次数当权重，命中才累加次数。计数持久化，达到上限就不再抽，概率0/1应稳定。返回events数组，元素有id/message/effects。组件只记录抽中次数和返回结果，不自行修改任何实体资源。禁止运行时eval、网络或系统调用，使用标准random即可。
```

## phase3/family-task.json

会话：`session-dd0d0b11-6a68-4bc0-a04f-f2163fc7d922`

```text
做一个可配置的家庭业务组件，挂在普通业务节点，mode分民政登记、家庭计划、医院三种，只暴露该mode对应工具，可用tool_enabled。依赖文档在dependencies。所有实体节点、时钟节点、地点地址、依赖组件ID、工具频道、行动花费都用config传入，人物数据仍在entity.profile.profile，不写死人物名字或节点ID。可信调用者用current_agent_id。
民政登记：双方成年、同地点、都各自调用同意与对方结婚的工具才登记，任何一方不能替另一方同意；已有配偶不能乱改，重复登记不重复扣费。登记后双方profile.spouse互指。
家庭计划：只允许在自己家且已婚的两人，各自同意要孩子后，给其中profile.gender为female的角色记录due_tick=当前tick+10，十个时刻也就是两天。每对最多一个孩子，返回预产日提示；不需要现实孕期。
医院：本人到期且亲自在医院时调用生产工具，新建一个独立AgentNode儿童，父母关系双向登记；未到期/没到医院/已经生过要明确拒绝或返回同一孩子，不能重复扣费或创建。新儿童的modules、execution、初始资料来自config.child_template，构造时填入姓名、gender、age_group=child、parents及当前place；新记忆文件独立且不复制父母记忆。孩子出生会说话，但本轮不能启动，由下一次脉冲自然参加。
创建后接上config.time_node到孩子和孩子到config.save_node的world.tick连接，并与医院地址双向在场连接，使用config指定的在场频道，门槛1/散度-1；调用backend.modules.refresh()注册新节点信号响应。
所有业务先验证前提，再用核心短事务扣除行动值和修改实体；每次默认1点。setup不读取其他未装配实例。README列清字段、工具和返回值。只做这个业务组件，不写网络配置或启动器，不要兼容旧实现。
```

## phase3/savepoint-task.json

会话：`session-3814933b-117b-4d81-bfe2-b6859241677c`

```text
做一个通用计数存档组件，挂在普通节点，收到world.tick新信号计数一次，同一个signal_id不重复计数。每到配置interval次就调用backend.dispatch("save",{"full":true})请求全量存档，默认5。保持count和last_signal持久化，别做整张网络初始化或NPC收尾逻辑。提供读取当前计数的内部操作。
```

## phase4/rules-task.json

会话：`session-9fd32687-6b9c-4148-8f31-b94e5d562cc1`

```text
做一个配置驱动的本地行动规则组件，挂在普通业务节点，只公开act(action,quantity=1)工具。它能通过配置用于挖矿、砍树、修理、休息、商店交易、酒馆消费，不在代码中写死这些行为。读取dependencies中实体/行动值/概率事件公开说明。
config指定address（这个业务所在地址）、channels、entity_module、action_module和rules字典。每个rule有简短description、cost（每次调用固定行动消耗）、requires_items、requires_profile，以及actor和place两组effects，effects使用entity.profile.adjust的coins/items/fields结构；quantity是1到100的正整数，物品和金币增量按quantity倍增，cost不按数量倍增，fields原样设置。requires_items表示每单位最低持有量，requires_profile按字段等值检查（用于仅成年人工作、只能在自己家休息）。place指业务所在地址的实体库存。
可信调用者用current_agent_id，不允许模型填身份；必须真实在address、具备双向在场连接且同频道才执行。先验证全部前提、库存/金币及行动值，再用backend.modules.transaction把调用者和地址的所有状态变更一起提交，失败一个都不改，也不扣行动值。具体业务只写进example/README演示配置，不要写网络预设。
可选events_ref={node,module}，成功动作后按rule.event_trigger（默认action）调用其draw(trigger,context)，把events的message一起返回。事件effects如为{coins,items,fields}，通过实体adjust应用到执行者；纯传闻可以没有effects。事件实例计数也应在同一短事务保护范围内。
返回ok/message/remaining/action/quantity/events和简明资源变化，拒绝明确说明原因和余额；工具描述要从本实例rules生成动作菜单，NPC无需再查询。不要实现模型循环、移动或家庭逻辑。测试覆盖缺钱缺货、AP不足、负数量、跨地点、只限自己家、资源原子性。
```

## phase4/transfer-task.json

会话：`session-a37c1d77-b3d6-44d9-8f8f-9845aa6e3eb3`

```text
做一个通用同场赠送组件，挂在每个Agent上，公开一个give工具：模型填正数金币/正数物品数量（可只填其中一种），含义是把调用者自己的资源送给本节点的收礼者，不能填发送者身份、不能取别人东西。可信发送者用current_agent_id。双方profile.place必须相同且真实双向在场，频道config指定。默认扣发送者1行动值，借钱可以通过发消息请求再由对方主动赠送，不自动欠债。依赖实体和行动值组件ID由config给。用核心短事务同时校验和扣除发送者物品金币、增加收礼者物品金币、扣行动值，失败不改一半。描述中显示收礼者姓名。工具拒绝0数量、负数、给自己或不足资源；返回发送成功的资源和剩余AP。不要实现聊天、商店或网络初始化。
```

## phase4-resumed/rules-task.json

会话：`session-9fd32687-6b9c-4148-8f31-b94e5d562cc1`

```text
之前宿主在另一批完成时关闭，打断了这项任务。请沿当前历史继续完成原始需求；已有完整文件不必重写。宿主会先验证现有产物，如果本次有验证日志请先修正。只编辑组件，别运行命令。
```

## phase4-resumed/transfer-task.json

会话：`session-a37c1d77-b3d6-44d9-8f8f-9845aa6e3eb3`

```text
之前宿主在另一批完成时关闭，打断了这项任务。请沿当前历史继续完成原始需求；已有完整文件不必重写。宿主会先验证现有产物，如果本次有验证日志请先修正。只编辑组件，别运行命令。
```

## phase5/movement-events-task.json

会话：`session-3bd56c46-1138-4ba2-80d6-37ccf92cc7d5`

```text
给现有移动组件加一个可选events_ref={node,module}配置。成功到达时调用这个组件的draw(trigger=arrive,context包含actor人物ID和place本地点ID)，把返回events中的message一并返回给NPC，作为到达时见闻。依赖chance.events的说明已经补进dependencies。若事件effects是{coins,items,fields}，用entity.profile.adjust应用到执行者。事件抽取次数、行动费和实体状态应在同一个短事务内；必须在更改在场接口之前处理可能失败的事件/效果，失败时人物位置、AP、资源及接口都不得不一致。没有events_ref时保持现有行为。不要硬编码具体事件，也不要写网络配置。更新清单、示例、README与测试，版本1.0.1。
```

## phase5/social-denial-task.json

会话：`session-389ad029-dfdf-4336-8da9-1ca8c2e2118f`

```text
集成时发现：对方移动后，框架先拒绝旧工具调用，talk里的友好提示到不了NPC。SDK现在提供通用on_tool_denied(name,actor,reason)回调，原生宿主只在曾经可见的工具后来不可达时调用它解释拒绝，不会执行talk。请在组件覆写这个回调：对于talk，如果双方位置不同，返回某人好像已经去了「地点名」，已经不在这里了，根据对方当前profile.place取真实名称；无法确认或不是位置问题时返回reason。只解释，不扣费、不发送消息、不修改state。原有talk正常行为和公开参数不变，补测试并更新文档，版本1.0.1。
```

## rough/rough-savepoint-task.json

会话：`session-b5bd2755-f774-4e8c-9845-7ed8ce23a1a5`

```text
帮我做个小镇存档组件，每个时刻的脉冲记一次，记到5次就存一次完整档，重启接着数，同一个脉冲别重复记。只做组件。
```

## social-final/social-place-name-task.json

会话：`session-37727412-7e19-4f78-8c98-9e451a70b550`

```text
真实集成测试发现一个小问题：on_tool_denied 返回了“林好像已经去了「place/home1」，已经不在这里了”。应把地点ID解析为 backend.network.nodes[receiver_place].name，例如“居民楼1”；节点不存在才回退ID或未知地点。只修这个展示问题，版本改1.0.2，加对应回归测试，别重写组件、别运行命令。
```

## production-final/production-cost-task.json

会话：`session-c870a0fe-e32d-48e9-87e8-3a759b2522fa`

```text
真实运行发现通用规则中 quantity 倍增产出但 cost 固定，会让持3把镐的人 act(mine,3)只花6AP产出9矿。请增加 rule.cost_per_unit 可选boolean配置，默认false表示交易整单按一次计费；true时实际cost=rule.cost*quantity，用同一个实际cost做检查、扣费、返回和拒绝说明。工具描述明确本规则每单位/每次的计费方式，所有其余行为不变。版本1.0.1。加测试：cost6 cost_per_unit=true quantity2余额10拒绝且资源AP不变，quantity1成功剩4；交易默认quantity3仍只扣1。只改本工作副本，不读旧业务代码，不运行终端。由宿主验证。
```
