# 查报告

需要查看受托节点的完整汇报、执行记录或归档成果时，先查索引，再按索引路径读取。

**例：查看某个节点的报告。**

调用 `datanet_reports_query`：

```json
{"node_id":"目标节点ID"}
```

默认查当前请求。查指定请求或委托分支时，加上 `root_request_id` 或 `delegation_id`，使用入口或委托返回的 ID。

在返回的 `items` 中选中所需委托；同一节点可能执行多次，可按任务、轮次、时间和状态区分。从该项取 `root_request_id`，从 `runs[].files` 取所需文件路径，然后调用 `datanet_report_read`：

```json
{"root_request_id":"所选项的请求ID","path":"所选运行的 files.report 路径"}
```

示例中的值替换为实际返回值。路径可直接使用，无需逐层找文件。

- `files.report`：完整最终汇报；`files.tools`：工具调用及结果。
- `files.error`：失败原因；`files.submission`：成员提交；`files.output`：Recorder 归档成果。只会列出实际存在的文件。
- 想看委托传递关系，将 `path` 设为 `topology.json`；按节点找运行可读 `node-index.json`。目录嵌套表示父子委托，同级序号表示发起顺序。

查询或读取返回 `has_more=true` 时，保持原参数，将 `offset` 设为 `next_offset` 继续。
