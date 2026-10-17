官方 DeepSeek Harness 0.2.0-rc.2 AgentLoop，增加 agent/prepare-context（组装请求前同步文本工具）、agent/tool-schemas waterfall（对本次模型工具定义应用作用域权限）和 agent/request-tail waterfall（请求临时尾部）。每次请求保存 datanet/request-tail 快照用于还原，无 surfaceOp，正文不进入 deriveMessages、历史压缩或下一次请求历史。对应 invariant 按历史 + 当次尾部快照核验。工具执行权限由官方 tools.guard 实施；工具及其他调度生命周期沿用官方实现。

压缩或其他 surface replacement 发生在工具装配之后时，下一次请求（包括溢出后的同一步重试）重新装配系统提示和工具清单，避免使用压缩前捕获的旧定义。工具回收策略由适配层的 ToolPermissions 管理，AgentLoop 仅识别原生 surface replacement 代次。
