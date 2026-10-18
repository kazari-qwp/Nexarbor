# 局部记录仓 records.store

一个通用的本地 JSON 记录组件。可挂在 NPC（`agent`）、容器、任务板、地点或任意 `node` 上，用同一份模块保存财产、行动点、身份、库存数量、任务状态等，不需要为每个对象单独写组件。清单的 `node_types` 同时声明 `node` 与 `agent`，两种真实节点都能装配和运行本模块。

- 不依赖其他模块，不导出 Agent 工具。
- 所有操作使用访问频道 `records`。
- 配置决定初始普通值、初始显式引用和数字最低值；运行结果分别保存在本实例的 `state.values` 和 `state.references`。
- 首次 `read` 或 `apply` 时才把 `config.initial` 与 `config.references` 深拷贝到状态，之后配置变化不覆盖已有运行状态。
- 每次成功 `apply` 最多保留最近 200 条带去重键的请求回执；回执同样把普通值与显式引用分开保存。

## 装配与配置

在节点上挂载组件 `records.store`，配置示例：

```json
{
  "initial": {
    "金币": 20,
    "行动点": 3,
    "身份": "商人",
    "库存": { "面包": 2, "水": 1 },
    "任务": { "状态": "未完成", "进度": 0 }
  },
  "references": [
    { "key": "home", "node_id": "house-01" },
    { "key": "spouse", "node_id": "npc-b" },
    { "key": "parent", "node_id": null }
  ],
  "minimum": {
    "金币": 0,
    "行动点": 0,
    "库存.面包": 0
  }
}
```

`initial` 是任意 JSON 对象，值可以是数字、字符串、布尔、对象、数组或 `null`，但不要在里面放住所、配偶、父母等节点关系字符串。`references` 是可配置多条键名的显式引用数组，每项为 `{ "key": "非空字段名", "node_id": "节点 ID 或 null" }`；`node_id` 在 Schema 中标记了 `format: "node-id"`，普通字符串不会被猜成节点 ID。`minimum` 是“字段名 → 数字”的字典；每次 `apply` 提交前检查已配置下限的普通数字字段，低于下限则整次请求失败且不修改任何字段。`minimum` 默认 `{}`。

只有首次初始化时才把 `config.references` 深拷贝到 `state.references`。重复引用键、引用项类型非法、以及引用键与 `initial` 中普通字段同名都会拒绝；已有 `values` 始终只保存普通 JSON 记录，不做旧字符串迁移。

仓库自带页面 `ui.html`，可编辑任意类型的初始字段、显式引用数组和数字形式的最低值；保存后写入网络草稿，需在客户端点击“应用网络”才影响运行实例。

## 操作

### read

参数必须为空对象 `{}`，返回：

```json
{ "values": { "金币": 20, "行动点": 3, "home": "house-01" } }
```

返回的是普通 `values` 与显式 `references` 按 key 合并后的业务视图，所以其他模块仍可直接用 `values.home`、`values.spouse` 读取节点 ID 字符串；引用字段不会出现在普通的 `state.values` 中。返回值是副本，调用方修改它不会影响仓内状态。

### apply

参数：

```json
{
  "set": { "身份": "守卫" },
  "deltas": { "金币": -5, "行动点": -1 },
  "expected": { "金币": 20, "身份": "商人", "home": "house-01" },
  "references": [
    { "key": "home", "node_id": "house-02" },
    { "key": "child", "node_id": "npc-child" }
  ],
  "key": "npc-a:buy-bread:0001"
}
```

`set`、`deltas`、`expected`、`references` 都可省略，`references` 默认 `[]`。执行顺序：

1. 若提供去重键，先查最近回执：键和完整参数都相同则直接返回上次快照的合并视图，`duplicate: true`，不重复扣钱；同一个键配不同参数会报错。
2. 先按**变更前**的普通 `values` 与显式 `references` 合并视图逐字段核验 `expected`；字段不存在或不一致则整次失败。此时尚未应用本次请求的 `references`、`set` 或 `deltas`。
3. 处理 `references`：按 key 新增或更新显式引用；同一请求内键重复、引用键与普通 `values` 字段同名都会拒绝。
4. 写入 `set`：已声明的引用字段更新 `state.references`，值必须是节点 ID 字符串或 `null`；其他字段写入普通 `state.values`。
5. 对 `deltas` 每个普通数字字段做加减；字段不存在按 `0` 处理，已有非数字（包括布尔值）会拒绝，引用字段不能做数值增减。同一普通字段同时出现在 `set` 和 `deltas` 时，先写入 `set` 值再叠加增减，例如 `set: {gold: 5}`、`deltas: {gold: 2}` 得到 `7`。
6. 校验所有配置了 `minimum` 的普通数字字段。
7. 全部通过才一次性提交，并返回 `{"values": 合并业务视图, "duplicate": false}`。

任何错误都不会留下半修改；业务错误以 `status: "error"` 和中文 `error` 返回。参数类型和频道权限由框架预检，非法类型或错误频道会直接拒绝。

### 去重键

接口约定并固定使用字段名 `key`。它是可选的字符串；相同 `key` 与相同 `set`/`deltas`/`expected`/`references` 再次提交时，直接返回上次快照并标记 `duplicate: true`，不会重复扣减；同一个 `key` 配不同参数会报错。没有旧字段别名，也不需要为同一次业务重试更换键。回执把普通 `values` 与显式 `references` 分开保存，`duplicate` 返回的 `values` 是原快照的合并业务视图。

## 节点引用与完整网络拷贝

住所、配偶、父母、子女等节点关系必须显式写进 `references`，不要在 `initial` 或普通 `set` 中直接放节点 ID 字符串。显式引用带有 `format: "node-id"` 的字段声明，完整网络拷贝（例如从网络 A 复制到网络 B）时可以按节点身份自动映射到新节点；普通字符串没有这层声明，既不会被自动映射，也不会被猜成节点 ID。已有旧状态中的普通字符串不会迁移或猜测，需要调用方通过 `apply.references` 显式补充。

读接口会合并返回，因此其他模块仍统一用 `values.home`、`values.spouse` 读取；需要区分普通字段与引用字段时，应查看本模块的 `state.references` 或回执的 `references` 数组。

## 跨节点业务事务

记录仓保证单个节点的一次 `apply` 原子完成。需要同时修改两个 NPC、或“扣款 + 加库存”这类跨节点业务时，由调用方组件在外层锁住所有会被修改的节点，再分别调用各节点的 `apply`。记录仓自己的节点锁是重入的：外层事务已锁住该节点时，再次进入 `apply` 属于正常嵌套锁，不会扩大锁集合；外层后续失败仍会让整批修改回滚。外层锁内出现失败时必须抛异常，让异常穿出锁作用域触发整批回滚，最后在锁外转成错误结果。

```python
from datanet.core.module_protocol import ComponentResult


async def transfer(ctx, activation):
    target_node = activation.parameters["目标节点"]
    try:
        async with ctx.network.lock_nodes([ctx.node_id, target_node], timeout=20):
            # 锁后重查，不要使用锁前的余额。
            source = await ctx.network.call(ctx.node_id, "records.store", "read", {})
            if source["status"] != "ok":
                raise RuntimeError(source["error"])
            balance = source["data"]["values"].get("金币", 0)
            if not isinstance(balance, int) or isinstance(balance, bool) or balance < 5:
                raise RuntimeError("金币不足")

            first = await ctx.network.call(
                ctx.node_id,
                "records.store",
                "apply",
                {
                    "deltas": {"金币": -5},
                    "expected": {"金币": balance},
                    "key": "transfer:out:0001",
                },
            )
            if first["status"] != "ok":
                raise RuntimeError(first["error"])

            second = await ctx.network.call(
                target_node,
                "records.store",
                "apply",
                {
                    "deltas": {"金币": 5},
                    "key": "transfer:in:0001",
                },
            )
            if second["status"] != "ok":
                raise RuntimeError(second["error"])
            # 后续若还有步骤失败，直接 raise；不要在这里 return error。
    except Exception as error:
        return ComponentResult(status="error", error=str(error))

    return ComponentResult(data={"完成": True})
```

要点：

- 锁住执行组件以及所有会被修改的节点，不只锁其中一个记录仓。
- 记录仓在自己的节点锁内再次加锁是重入的，外层的共同事务仍然有效。
- 每个子操作使用稳定且互不相同的去重键 `key`，便于网络重试时避免重复扣减；同一业务请求重试要复用同一个键和相同参数。
- 不要在持锁时等待模型、独立信号或外部网络，也不要依赖记录仓内部备份回滚外部效果。
