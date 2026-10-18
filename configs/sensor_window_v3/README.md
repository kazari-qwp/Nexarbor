# 滑动窗口数值统计网络

一个最小网络预设：入口 Agent 把用户提交的连续数值转交给测量节点，测量节点只保留最近 N 个值，并公开个数、最小值、最大值和算术平均值。统计完全由已发布的通用组件 `number.window` 完成，网络文档和 Agent 提示词中不保存数值，也不做统计计算。

## 节点与连接

| 节点 | 类型 | 组件 | 职责 |
|---|---|---|---|
| `root`（入口） | Agent | `tools.collector` | 接收用户输入，收集测量节点的工具并提交数值/读取统计 |
| `meter`（测量节点） | node | `number.window` | 在本地有界窗口中保存最近 N 个数值并返回统计 |

`root → meter` 有一条单向边，频道为 `measurement`、`tools`，阈值 1、倍率 1。数值写入和统计读取都从入口发起，因此不需要反向边；反向不可达也是预期的访问限制。

## 复用与新组件

- 复用的核心能力：`tools.collector` 负责按可达路径收集并调用 `number.window` 暴露的两个公开工具；节点边、Agent 执行配置、访问频道均使用核心协议。
- 新造组件：`number.window`（滑动窗口数值统计，v0.1.0），提供公开操作 `push` 与 `read`、本地有界状态、中文配置前端和 Agent 工具“提交数值”“读取统计”。

## 组件接口

`number.window` 挂载在 `meter` 上，操作频道为 `measurement`，访问强度 2。

- `push`：参数 `{"value": 数值}`，可选 `{"key": "请求键"}`。追加到窗口并返回 `count/min/max/mean/window_size/duplicate`；相同键和相同数值重试不会重复追加。
- `read`：无必填参数，返回当前窗口的 `count/min/max/mean/window_size/values`。
- 窗口为空时 `count=0`，`min/max/mean` 为 `null`；`mean` 是窗口内数值的算术平均，保留浮点结果。
- 本地状态只保存最近 `window_size` 个数值，不保留无限历史。

## 调节窗口大小 N

在客户端打开 `meter` 节点的 `number.window` 配置，修改“窗口容量”（`window_size`，整数 1..1000，默认 3）。前端会校验范围；修改后下一次 `push`/`read` 即按新容量统计。

## 使用方法

1. 在入口与 Agent 对话，每提供一个数值，入口会调用“提交数值”工具提交到 `meter`。
2. 询问统计时，入口调用“读取统计”工具并转告 `count/min/max/mean`。
3. 也可以在客户端直接查看/调用 `meter` 上的 `push`、`read` 操作。

入口 Agent 的执行配置使用 `harness` 执行器，准备步骤为空，工具由本节点的 `tools.collector` 提供；未启动日常客户端，也未运行任何真实外部工具。

## 测试结果（测试副本，candidate）

在测试副本中依次从 `root` 调用 `meter` 的 `push`：1、2、3、10，容量 N=3，最后读取得到：

```
count=3, min=2, max=10, mean=5, values=[2, 3, 10]
```

同时验证：

- `root` 通过 `tools.collector` 能看到并调用“提交数值”“读取统计”两个工具，读取结果同上。
- 跨节点可达限制：从 `meter` 反向调用 `root` 被拒绝（`PermissionError: Component is outside the current graph view`）；从 `root` 以未授权频道 `tools` 调用 `meter` 被拒绝（`PermissionError: Operation channel is not granted`）。
- 组件自身另有 12 项真实测试通过，覆盖空窗口、滚动保留、自定义容量、非法/非有限数值、错误频道、状态有界、实例隔离和同键并发幂等。
