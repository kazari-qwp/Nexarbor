# 文本便笺 notes.text

挂在 `text_file` 文本节点上的通用公共便笺。业务模块和 Agent 都可以追加、读取、整体覆盖或清空本节点正文，用作公共笔记、讨论草稿或成果摘要。

正文不是模块私有状态，而是文本节点的主键 `content`：实现通过 `ctx.read({'method':'key','key':'content'})` 读取、通过 `ctx.write('content', ...)` 写入，并检查返回的 `NodeResult.status`。因此其他按文本读取的组件（如上下文组装器的 tail/context 频道）也能直接读到同一份正文。

## 装配

```json
{
  "notes.text": {
    "config": {
      "title": "便笺",
      "max_chars": 20000,
      "separator": "\n\n"
    },
    "state": {},
    "access": {
      "strength": 2,
      "channels": ["notes", "notes"]
    }
  }
}
```

装配到 `text_file` 节点。写入类操作走 `notes`，读取走 `notes`；调用方需要到该节点的可达路径与对应频道授权。模块本身不调用其他节点，`requires` 为空。

## 配置

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `title` | 字符串 | `便笺` | 读取时返回的标题，用于区分不同用途。 |
| `max_chars` | 整数，1000..200000 | `20000` | 正文上限。追加或覆盖后超出时拒绝写入，旧正文保持不变。 |
| `separator` | 字符串 | `"\n\n"` | 追加时插在旧正文与新内容之间；正文为空时不加分隔。可设为空字符串。 |

## 操作

### append（频道 `notes`）

参数：

```json
{ "text": "讨论要点", "key": "会议-1" }
```

- `text`：必填，1..8000 字符。
- `key`：可选幂等键。

把 `text` 追加到正文末尾：正文非空时先插入 `separator`，正文为空时直接写入。若追加后长度超过 `max_chars`，返回 `status=error` 且不写入任何内容。

返回：

```json
{ "version": 3, "length": 128, "appended": 18, "duplicate": false }
```

- `version`：写入后的正文版本；每次实际写入加一。
- `length`：写入后的正文字符数。
- `appended`：本次实际追加的字符数（含分隔符）；重复请求为 0。
- `duplicate`：是否命中相同幂等键与相同内容。

### replace（频道 `notes`）

参数：

```json
{ "text": "重写后的完整正文", "key": "草稿-7" }
```

`text` 必填，0..`max_chars` 字符；空字符串表示清空正文（仍算一次实际写入并推进版本）。超过配置上限时拒绝且不改动旧正文。

返回：

```json
{ "version": 4, "length": 9, "duplicate": false }
```

### read（频道 `notes`）

无参数。返回：

```json
{ "title": "便笺", "content": "当前正文", "version": 4, "updated_at": "2026-10-20T08:00:00+00:00" }
```

`updated_at` 为最近一次实际写入的 UTC ISO 时间；从未写入时为空字符串。

### clear（频道 `notes`）

无参数。清空正文并推进版本，返回：

```json
{ "version": 5, "cleared": 9 }
```

`cleared` 是本次清掉的字符数。清空只动正文，不清幂等回执，因此旧键仍会按原内容判重。

## 幂等与并发

`state.seen` 保存最近 200 条 `{key, fingerprint}` 回执，指纹由操作类型与正文组成：

- 同一便笺上相同 `key`、相同操作、相同正文的再次请求直接返回 `duplicate: true`，不重复写入，也不推进版本。
- 相同 `key` 配不同内容（或不同操作）返回错误，正文不变。
- 键空间属于本便笺实例，不同便笺互不影响。

追加、覆盖和清空都在 `ctx.network.lock_nodes([ctx.node_id], timeout=20)` 的短锁内重新读取正文、判断重复、写入并提交状态。两个并发 `append` 不会互相覆盖；同键并发追加只成功一次。锁只包住这一次同步读改写，不包住模型思考或其他网络等待。

## Agent 工具

`agent_tools` 提供两个入口，均复用已声明操作：

| 工具 | 操作 | 说明 |
|---|---|---|
| `append`（追加笔记） | `append` | 把一段文字追加到便笺末尾。 |
| `read`（读取笔记） | `read` | 读取标题、正文、版本和最后更新时间。 |

工具权限仍由所在节点、调用路径和频道决定，不额外扩大访问范围。

## 限制

- 只支持 `text_file` 节点；普通 `node`/`agent` 没有本地文本写入能力，不能挂载。
- 字符数按 Python 字符长度计算，不按字节或显示宽度。
- 正文就是文本节点内容，模块不保留历史版本；需要历史请配合记录仓或知识集合。
