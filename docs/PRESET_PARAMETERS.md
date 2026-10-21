# 网络预设的数量参数

当前框架只提供一个整数参数 repeat_unit_count，范围 1–100。未声明或 null 的预设没有数量输入，按普通预设拖入。

支持的 v8 网络文档在 network 内声明：
```json
{"repeat_unit_count":3,"repeat_unit":["member"]}
```

repeat_unit 是一个单元包含的节点 ID，亚节点后代自动包含。其余节点为共享部分。右侧详情只需填写数量，不要求用户写表达式。拖入先调用核心 preset_expand 生成独立快照，再走原有放置逻辑；每次放置的 ID、文本、数据文件和目录均独立。所属关系、内部边、模块 Schema 声明的节点引用、prepare 与 tool_sources 都随单元重映射。

固定对象指向重复单元的边扩展到每份单元；单值配置引用保持指向第一份。各单元连接同一组共享对象，单元内部链接指向自身的新副本。没有声明的外部节点仍遵循原来的 A/B 复制规则。展开只生成数据，不运行 Agent 或调用工具。

数字随书签、历史缓存和磁盘预设保存，历史按配置区分数量。右侧未保存的数量也立即用于当前预设的拖动；Save 可把该配置保留为书签，再按 S 写入当前网络预设目录。原预设文件不会被仅一次拖动覆盖。

示例在 [预设组网项目](../projects/preset-compatibility/) 的 `network_presets/fragments/`：`discussion.json` 和 `execution.json` 分别定义讨论组与执行组，成员可重复，组内公共资源只保留一份。该项目初始只有根节点与管理员；[完整讨论与协作项目](../projects/discussion-collaboration/) 保留已组装拓扑及相同预设。

实现：python/datanet/core/preset_repetition.py。边界：最多 100 个单元、展开后最多 10000 个节点。验证包含共享对象、嵌套亚节点、节点引用、独立存储、ID 冲突、可选字段及旧格式兼容。
