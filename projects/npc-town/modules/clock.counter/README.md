# 时钟与计数触发器

模块 ID：`clock.counter`。把收到的信号推进为可读的轮次时钟，可用于小镇五时刻、每若干次信号存档等场景。支持挂载在 `node`、`text_file`、`pulse` 上。

## 配置

- `signal_channels`：接收信号的频道，默认 `["tick"]`。声明在模块的 `signals` 中，按配置生效。
- `labels`：一轮内的时刻名称，默认 `["清晨","上午","下午","傍晚","夜晚"]`。不同实例可用不同名称。
- `initial_tick`：尚未收到信号时的计数，默认 `0`，必须是非负整数。
- `checkpoint_every`：每多少次计数调用一次 `runtime:checkpoint`，默认 `0` 表示禁用。
- `write_text`：是否把中文时间写入本节点文本，默认 `false`。

读取操作 `read` 使用 `info`、`tick` 频道，参数为空，返回：

```json
{"tick": 1, "day": 1, "slot": "清晨"}
```

初始 `tick=0` 显示为第 1 天第一个时刻。每收到一个新信号先锁本节点，再计数并发布 `{tick, day, slot}` 元数据。相同 `signal_id` 经多条路径到达只计一次；状态只保留最近 200 个信号 id。

重试操作 `flush` 使用 `runtime.checkpoint` 频道，参数为空，返回 `{"checkpointed": 是否执行了存档, "tick": 当前计数}`。它不会推进时钟，只处理已登记且尚未完成的待办存档。

## 存档

计数到达 `checkpoint_every` 的倍数时，组件先在锁内把 `pending_checkpoint` 记为真，释放节点锁后再用本节点自己的 access 授权调用 `runtime:checkpoint`，参数为 `{"full": true}`，频道固定为 `runtime.checkpoint`。不会沿用信号来源、直接调用者或最初发起者的权限，也不会借用信号原频道的授权。未配置 `checkpoint_every` 时不触碰运行时。

存档调用失败（例如节点尚未提供该工具）会让信号分支直接抛出异常，传播器把该分支标记为失败并停止向后传播；不会返回业务 `error` 封套来假装信号处理成功。失败时 `pending_checkpoint` 保持为真，补齐授权后可调用 `flush` 重试；成功后会清除待办，重复 `flush` 不会再次存档。

装配时应同时给模块 access 和本节点 `offered_tools` 授权 `runtime.checkpoint`，例如：
```json
{"ref": "runtime:checkpoint", "channels": ["runtime.checkpoint"]}
```
tick 信号波和入边仍然只需要 `tick` 频道；存档调用只使用本节点明确获得的工具与授权。

## 文本输出

`write_text=true` 时，经 `ctx.write` 写入本节点文本的 `content` 主键（`TextFileNode` 的实际主键），内容如 `第1天 清晨`。挂载在普通 `node` 上时，核心会返回不支持本地写入；此时应关闭该选项或改挂到 `text_file`。

## 装配建议

- 挂在 tick 链开头：每层波到达时先推进时钟，后续节点读取统一时间。
- 挂在 tick 链尾：只负责计数和定期存档，不改变上游时序。
- 多个场所可各挂一个实例，用 `labels`、`initial_tick`、`checkpoint_every` 区分，不必为每个场所写新组件。
