# family.household · 可配置的家庭业务

挂在**普通业务节点**（`node`）上的家庭业务组件，按实例配置的 `mode` 只暴露一个工具：

| `mode` | 含义 | 暴露的工具 |
| --- | --- | --- |
| `civil` | 民政登记 | `register_marriage(partner)` |
| `family` | 家庭计划 | `plan_child()` |
| `hospital` | 医院接生 | `give_birth(name, gender)` |

人物资料始终读写依赖组件 `entity.profile` 的 `profile`；调用者身份取
`current_agent_id()`，模型不能把“我是谁”作为参数填进来。所有实体节点、地点节点、
时钟节点、依赖组件 ID、工具频道和行动值花费都来自 `config`，组件里不写死任何
人物、地点或应用节点 ID。

## 挂载

- 模块 ID：`family.household`，版本 `1.0.1`。
- 支持节点：`node`（普通业务节点）。
- `requires`：`entity.profile`、`action.points`、`time.text`；宿主按依赖顺序加载，
  但不会自动挂载。装配者需要：
  - 在每个参与人物节点上挂 `entity.profile` 与 `action.points`；
  - 在时钟节点上挂 `time.text`（`family`、`hospital` 模式需要）；
  - 在业务节点上挂本组件，并把本组件的 `channels` 接到需要调用工具的 Agent。
- 同一个业务节点只挂一个本组件实例；换模式就换一份配置。

```python
backend.modules.mount('service/civil-registry', 'family.household', {
    'mode': 'civil',
    'channels': ['family.civil'],
    'place': 'place/civil-registry',
    'presence_channel': 'presence',
    'entity_component': 'entity.profile',
    'action_component': 'action.points',
    'adult_age': 18,
    'costs': {'register_marriage': 1},
})
```

可运行示例见 `example.json`（民政登记）。

## config 字段

| 字段 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `mode` | `"civil"` / `"family"` / `"hospital"` | 是 | — | 决定本实例只暴露哪把工具。 |
| `channels` | string 数组，非空且不重复 | 是 | — | 本工具允许的访问频道。频道交集与强度由网络核心检查，组件不重复实现传播。 |
| `place` | string | 是 | — | 本模式的地点节点 ID：民政登记处 / 夫妻自己家 / 医院。工具会要求人物 `profile.place` 等于这个 ID，并核实真实在场连接。 |
| `presence_channel` | string | 是 | — | 人物与 `place` 之间双向在场连接的频道；三种模式都必填，用于核实真实在场，不只看 `profile.place`。 |
| `entity_component` | string | 是 | — | 人物资料组件 ID，通常为 `entity.profile`。 |
| `action_component` | string | 是 | — | 行动值组件 ID，通常为 `action.points`。 |
| `clock_node` | string | `family`、`hospital` 必填 | — | 时钟节点 ID。 |
| `clock_component` | string | 否 | `"time.text"` | 时钟组件 ID；调用它的 `get_tick`。 |
| `time_node` | string | `hospital` 必填 | — | 向孩子发 `world.tick` 的时钟/脉冲节点 ID。 |
| `save_node` | string | `hospital` 必填 | — | 接收孩子 `world.tick` 的存档/脉冲节点 ID。 |
| `child_id_prefix` | string | 否 | `"child"` | 孩子节点 ID 前缀；最终 ID 为 `前缀/姓名`，重名时追加 `-2`、`-3`。 |
| `adult_age` | integer ≥ 0 | 否 | `18` | 民政登记的成年年龄；`profile.age_group` 为 `child`/`minor` 时一律不算成年。 |
| `due_ticks` | integer ≥ 1 | 否 | `10` | 家庭计划从双方同意到预产的 tick 数。 |
| `ticks_per_day` | integer ≥ 1 | 否 | `5` | 一天几个时刻，只用于把 `due_tick` 换算成“第几天”的提示。 |
| `costs` | object | 否 | 各键 `1` | 各工具成功操作时扣除的行动值：`register_marriage`、`plan_child`、`give_birth`。 |
| `child_template` | object | `hospital` 必填 | — | 新建孩子 Agent 节点的模板，见下。 |

### `child_template`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `memory_path` | string | 是 | 相对运行目录的独立记忆文件路径，必须包含 `{node_id}` 或 `{name}` 占位符，保证每个孩子记忆独立。 |
| `memory_text` | string | 否 | 新记忆文件的初始文本，默认空串。不会读取或复制父母记忆。 |
| `description` | string | 否 | 孩子 Agent 节点的 `description`。 |
| `profile` | object | 否 | 孩子初始资料字段；先合并 `modules[entity_component].profile`，再合并本字段，姓名/gender/age_group/parents/place 最后由运行时覆盖。 |
| `management_parent_id` | string | 否 | 孩子节点的管理归属节点 ID；配置时必须已存在，创建后写入孩子的 `management_parent_id`，避免无主节点。 |
| `execution` | object | 是 | 写进孩子节点的执行绑定，例如 `{"executor":"harness","strength":2,"max_steps":12,"timeout_seconds":90}`。 |
| `modules` | object：模块 ID → 配置 | 是 | 孩子节点要挂载的模块配置；**必须包含 `entity_component` 对应的配置**，其 `profile` 会被动态字段覆盖。 |

构造孩子时动态填入：

```json
{
  "name": "孩子姓名",
  "gender": "调用时传入的 gender",
  "age_group": "child",
  "parents": ["接生者节点ID", "配偶节点ID"],
  "place": "医院节点ID"
}
```

`child_template.modules[entity_component].profile` 和 `child_template.profile` 里其余初始资料会保留，
上面的动态字段优先。

## 工具与返回

工具频道来自 `channels` 配置；每次调用的返回都是可 JSON 序列化的对象，业务拒绝返回
`ok=false` 与 `reason`，不抛异常，也不扣行动值。

### `register_marriage(partner)`

参数：`partner`：对方的 Agent 节点 ID（string，非空）。

前提（全部满足才可能登记）：

1. 调用者与对方节点都存在；
2. 双方的 `profile.age` 达到 `adult_age`，且 `profile.age_group` 不是 `child`/`minor`；
3. 双方都没有其他配偶记录；
4. 双方的 `profile.place` 都等于 `config.place`（登记处）；
5. 双方与该登记处之间都有 `presence_channel` 上的**双向真实连接**；只改 `profile.place`
   而没有连接会被拒绝。

登记是**两次独立同意**：双方各自以自己的身份调用 `register_marriage`，任何一方都不能替
另一方同意。第一次调用只记录同意并扣一次行动值；对方亲自调用后才完成登记，并把双方
`profile.spouse` 互指。已互为配偶后重复调用返回 `already=true`、`charged=0`，不重复扣费。
同一个人重复同意不会重复扣费；对新的对象表示同意会撤销自己之前未完成的同意。

返回字段：

```json
{
  "ok": true,
  "registered": true,
  "waiting": false,
  "already": false,
  "couple": ["npc/a", "npc/b"],
  "charged": 1,
  "remaining": 4,
  "message": "双方已各自同意，登记完成，你们的资料已互指为配偶。"
}
```

等待对方时：`registered=false`、`waiting=true`、`partner`、`charged`（首次为花费，
重复同意为 0）。拒绝时：`ok=false`，`reason` 可能为 `no_caller`、`unknown_caller`、
`invalid_partner`、`same_person`、`unknown_partner`、`profile_unavailable`、
`spouse_conflict`、`not_adult`、`place_missing`、`wrong_place`、`not_present`、`insufficient`。

### `plan_child()`

无参数。调用者与配偶必须是**互相登记**的夫妻；双方 `profile.place` 与
`profile.home` 都必须是 `config.place`（自己家），并且双方都与这个家保持
`presence_channel` 上的双向真实连接；这对夫妻还需要没有待产记录或孩子。双方各自调用
一次表示同意；第二次同意后，为其中 `profile.gender == "female"` 的一方写入
`due_tick = 当前 tick + due_ticks`（默认 +10，按默认 5 个时刻一天即两天）。每对最多
一个孩子。

返回字段：

```json
{
  "ok": true,
  "planned": true,
  "waiting": false,
  "partner": "npc/husband",
  "mother": "npc/wife",
  "due_tick": 13,
  "due_day": 3,
  "charged": 1,
  "remaining": 4,
  "message": "预产期已记录：10 个时刻后（约 2 天，第 3 天，due_tick=13）。"
}
```

第一次同意返回 `planned=false`、`waiting=true`、`charged`（首次为花费，重复为 0）。
拒绝的 `reason` 可能为 `not_married`、`spouse_missing`、`wrong_place`、`wrong_home`、
`not_present`、`already_has_child`、`already_planned`、`no_female`、`clock_unavailable`、
`insufficient`。

### `give_birth(name, gender)`

参数：`name`（孩子姓名，非空，≤ 40 字符，不含斜杠/反斜杠/控制字符）、`gender`
（孩子 gender，非空字符串）。

前提：调用者本人有 `profile.due_tick`；当前 tick 已到或超过 `due_tick`；调用者
`profile.place` 等于 `config.place`（医院），并与该医院有 `presence_channel` 上的
双向真实连接；与配偶的 `spouse` 记录互指；并且这台医院还没给本人记录过孩子。

成功后：

1. 新建独立 `AgentNode` 孩子（自己的记忆文件，不复制父母记忆）；
2. 从 `child_template.modules` 挂载模块，把姓名、gender、`age_group=child`、
   父母 ID、当前医院地点写进孩子的 `profile`；
3. 双向登记父母关系：孩子 `profile.parents`，父母双方 `profile.children`；
4. 接上 `time_node → 孩子` 和 `孩子 → save_node` 的 `world.tick` 连接（门槛 1）；
5. 医院 ↔ 孩子双向在场连接，使用 `presence_channel`、门槛 1；孩子节点散度为 -1；
6. 调用 `backend.modules.refresh()` 注册新节点，孩子本轮不启动，下一次脉冲自然参加；
7. 把接生者 `profile.due_tick` 置为 `null`；
8. 如果配置了 `child_template.management_parent_id`，把它写入孩子的
   `management_parent_id`；该节点必须已存在，否则在创建前拒绝。

返回字段：

```json
{
  "ok": true,
  "created": true,
  "already": false,
  "child": "child/小满",
  "child_name": "小满",
  "child_gender": "female",
  "parents": ["npc/mother", "npc/father"],
  "place": "place/hospital",
  "charged": 1,
  "remaining": 4,
  "message": "孩子「小满」已在「医院」出生，父母关系已双向登记；孩子本轮不会启动，下一次脉冲会自然参加。"
}
```

已经生过时返回 `ok=true`、`created=false`、`already=true`、同一个 `child`、`charged=0`，
不重复创建、不重复扣费。拒绝的 `reason` 可能为 `no_due`、`no_spouse`、`not_married`、
`not_due`、`wrong_place`、`place_missing`、`not_present`、`wiring_missing`、
`management_missing`、`child_missing`、`insufficient`、`create_failed`、`birth_failed`。

## 状态

```json
{
  "marriage_consents": {"<夫妻对键>": ["npc/a"]},
  "family_consents": {"<夫妻对键>": ["npc/wife"]}
}
```

只保存尚未完成的“各自同意”。夫妻对键由两个节点 ID 排序后拼接，不需要装配者提供。
`setup()` 只补缺失字段，不读取其他未装配实例。已完成的登记、配偶、预产期、孩子列表
都在 `entity.profile` 的人物资料里，随人物节点存档。

## operations 与 signals

- `operations`：空。尚无需要其他组件调用的公开操作。
- `signals`：空。本组件不响应信号、不生成信号，也不实现传播。
- 本组件只在 `hospital` 成功接生时调用 `backend.modules.refresh()`，用于注册新节点的
  通用信号绑定，不执行任何业务。

## 行动值与事务

- 所有业务先验证前提，再在 `backend.modules.transaction(...)` 的短事务里扣除行动值并
  修改实体资料；`civil`/`family` 的同意记录也在同一事务里写入本组件状态。
- 每次成功操作默认扣 1 点，可用 `costs` 按工具配置；余额不足返回 `ok=false`，不扣、
  不改资料。
- `hospital` 必须先在网络里创建节点，再进入扣费事务；扣费失败或事务异常时会移除本次
  创建的孩子节点、连接、已挂模块和记忆文件，尽量不留下半个孩子。

## 限制与装配注意

- `civil` 要求双方都在 `config.place` 这个登记处并与它有双向在场连接；`family` 要求双方
  `profile.home` 与 `profile.place` 都等于 `config.place` 这个自己家，并都与家有双向在场
  连接；`hospital` 要求本人在 `config.place` 这家医院并与医院有双向在场连接。只伪造
  `profile.place` / `profile.home` 而没有真实连接会被拒绝。
- `presence_channel` 上的连接必须由装配者或移动组件真实建立（人物 → 地点和地点 → 人物
  两个方向都要有）；本组件只核实连接，不替装配者补连接。
- 成年人判定依赖 `profile.age`（数字）和 `profile.age_group`；缺少 `age` 的人物不会被
  当作成年人。
- `family` 只用 `profile.gender == "female"` 认定预产方，不模拟现实孕期，也不处理多胎。
- 每对夫妻只有一个孩子：以双方 `profile.children` 和 `profile.due_tick` 判断，跨
  `family` / `hospital` 实例仍然生效，因为资料存放在人物节点上。
- 新建孩子不会自动绑定宿主执行器会话；`child_template.execution` 和模块配置需由装配者
  按实际宿主填写，孩子的 `module` 配置也必须能在当前宿主加载。
- 记忆文件路径必须留在 `backend.directory` 内；`memory_path` 需要 `{node_id}` 或 `{name}`
  占位符，防止不同孩子共用一份记忆。
- 不写整张网络、不生成启动器，也不兼容旧实现。
- 依赖宿主自带的 `datanet` 运行时和 `jsonschema`，不需要新增依赖。
