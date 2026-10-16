# 配置信息提供器

模块 `information.provider` 显式挂在节点上；共用一份实现，无节点类型分派。不暴露 Agent 工具。无模块时核心 `get_information(context)` 返回 None。

```json
{"fields":{"姓名":"/name","性别":"/extensions/npc/gender"}}
```

字段使用统一元数据的 JSON Pointer，缺失字段跳过。节点以自身身份读取元数据，仅发布配置选择的字段；这是一份明确的公开投影，不返回完整私有元数据。可选 `labels_by_hops: {"1":"本地","2":"相邻"}` 根据收集器传入的实际路径标记。标签含义由应用配置，强度仍负责访问权限。

只有信息收集器建立的内部访问上下文能调用提供器；该入口不注册为 Agent 工具或 RPC。卸载模块后恢复默认无信息。
