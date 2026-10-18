# 滑动窗口数值统计

`number.window` 在单个 `node` 或 `agent` 实例的本地状态中维护一个有界数值窗口，并通过 `measurement` 频道提供两个操作：

- `push`：参数 `{value: number, key?: string}`，追加一个有限数值并返回当前窗口统计。
- `read`：无参数，返回当前窗口统计和窗口内数值。

窗口为空时，`count` 为 `0`，`min`、`max`、`mean` 均为 `null`。`count` 是窗口内实际数值个数（不超过 `window_size`）。`mean` 是窗口内数值之和除以实际个数，保留浮点结果，不做四舍五入。

## 装配

组件默认访问配置为频道 `measurement`、强度 `2`，可装配到普通节点或 Agent。示例：

```json
{
  "config": {"window_size": 3},
  "state": {},
  "access": {"strength": 2, "channels": ["measurement"]}
}
```

## 可调参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `window_size` | 整数 | `3` | 窗口容量，范围 `1..1000`；只保留最近这么多数值。 |

配置可在组件前端“滑动窗口数值统计配置”中修改，写入网络草稿后需应用网络才影响运行实例。运行中把容量调小时，下一次访问会立即丢弃较早的值。

## 使用

提交数值：

```text
push {"value": 1}
push {"value": 2, "key": "样本-001"}
```

返回示例：

```json
{"count": 2, "min": 1, "max": 2, "mean": 1.5, "window_size": 3, "duplicate": false}
```

读取统计：

```text
read {}
```

返回 `count`、`min`、`max`、`mean`、`window_size` 和按提交顺序排列的 `values`。

## 幂等与边界

- `key` 可选。相同 `key` 与相同 `value` 重试时不重复追加，返回 `duplicate: true` 和当前窗口统计；相同 `key` 提交不同 `value` 会返回中文业务错误。
- 去重回执保存在本地状态中，只保留最近 200 条，因此非常久远且已被淘汰的请求键可能再次被当作新请求。
- `value` 必须是有限数值；`NaN`、`Infinity`、`-Infinity` 会被拒绝。
- 状态中只保存窗口数组和有限长度的回执数组，不保存无限历史。

## 工具

组件向 Agent 提供中文工具“提交数值”（`push`）和“读取统计”（`read`），工具沿用公开操作及其参数约束，不额外扩大访问权限。
