# 使用知识库

收到任务后，用 kb_task 保存原始需求：mode=agent 自行判断，read 仅检索，write 归档。保存资料也可直接用 kb_ingest，支持内容或工作区内的 CSV、JSON、TXT、Markdown 文件；file_path 的相对路径以应用工作区为起点。已知集合时指定 collection，已有路由会直接复用；否则返回 intake_id，由你选择集合并提交。

简单查询使用 kb_catalog、kb_search、kb_query、kb_fetch。导出记录使用 kb_export；Wiki 集合可选 format=wiki 生成可浏览的站点。

复杂任务可用 datanet_spawn_helper 创建助手，无必填参数。components 可选 csv、sqlite、rag、wiki 的组合：不填则继承可授予的业务权限，填写则限制写入类型；读取来源仍受原有读取范围限制。read 模式的助手只有读取能力。助手不能继续创建助手。

创建结果包含助手、原始任务和交付文档的节点 ID；用 datanet_send_message 下达分工并附这些引用。用 task_document_read 读取原始任务或交付文档，task_document_write 只写自己的交付文档。核查助手交付后再提交结果。引用知识记录时，sources 每项对应一条记录：node_id、version 沿用 kb_fetch 的返回值，locator 只填该记录 ID，不填说明文字或多个 ID。引用任务或交付文档时，node_id 填文档节点，locator 可标文中位置。receipts 只填本任务实际存储返回的记录；只读任务不填。无需反复转述完整内容。
