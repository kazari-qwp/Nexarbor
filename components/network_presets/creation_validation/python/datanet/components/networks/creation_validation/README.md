# 创建与委托最小验证

从项目根目录运行：

```powershell
python -m datanet.components.networks.creation_validation.run
```

使用项目 `.env` 的 DeepSeek 配置真实调用模型。根 Agent 读取目录并选择预设、创建实验子网络、单独挂载子 Agent、委托项目 A 合格率分析；子 Agent 调用真实 CSV/SQLite 实验组合工具。不会修改原实验数据。

结果保存到 `.models/research/creation_validation/<运行ID>/`：

- `report.json`：最终回答、根工具顺序、模型请求/响应轨迹、子工具实际统计及原网络对照。
- `network.json`：完成创建后的网络快照。
- `nodes/`、`agents/`：本次创建配置与独立提示词。

验证检查必需创建和委托工具均被调用、恰好创建一个子 Agent、子 Agent 实际调用分析工具且收到正确统计、提示词隔离及不继承创建权限。委托使用独立会话，通过API请求轨迹核验子 Agent 工具执行，不能只检查它持久会话中的消息。

此验证发送提示词、任务、规则和汇总统计到配置的 DeepSeek API，不记录 API Key。它是一条成功路径检查，不覆盖并发、断电恢复或所有权限错误场景。模型答案中的进一步建议只是生成内容，验证依据是实际工具返回的统计。
