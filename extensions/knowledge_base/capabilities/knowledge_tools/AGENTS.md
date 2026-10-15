# 知识库

用 kb_catalog 查找集合；数据库筛选、排序与分组统计使用 kb_query。kb_search 查找知识入口，kb_fetch 按需读取原文或指定版本。已知集合时直接查询。

kb_query 仅用于 SQLite。计数用 aggregate={"function":"count"}；求和、平均值、最小值、最大值还须在 aggregate 内填写 field，fields 只选择返回列。CSV 的条件筛选用 kb_search 的 filters。

归档前先找现有集合。确需新集合时用 kb_create_node：CSV 适合简单且少更新的表格，SQLite 适合持续更新和条件查询，RAG 适合需要语义查找的文档和零散文本，Wiki 适合整理后的知识和记忆。完整文档与独立碎片可按用途分别建 RAG 集合，不必为了切片破坏原文。碎片保留来源、日期等已有信息，不补造章节。结构化集合的 schema 填字段及 string/integer/number/boolean/object/array 类型；CSV 导入按声明的字段类型转换，编号等需要保留前导零的字段选择 string。路径和连接自动生成。

有 intake_id 时，用 kb_intake 读取待归档资料预览（可用 offset、limit 分页），再用 kb_store 指定 collection 和 intake_id 完成归档。混合批次可用 indices 选择本次归档的条目位置，直到 remaining_indices 为空。直接保存内容时填写 collection 和 content。资料可按稳定 key 更新；重复内容会复用记录。

Wiki 引用了已有资料时，sources 填来源记录 ID。来源变化后，kb_fetch 的 needs_refresh 会提示需要整理。更新和删除须先读取当前版本，再传 expected_version。

整理 Wiki 前用 kb_wiki 读取 ingest 指南；检索页面可选 action=search，检查链接和过期来源用 action=lint。维护流程复用 llm-wiki，操作映射会与原版指南一起按需加载。

RAG 的关键词索引始终可用。语义检索使用应用统一配置的嵌入模型；索引未就绪或配置缺失时会明确返回状态。需要原始资料时使用 kb_fetch 返回的 original_path。

检索命中只是入口。matches 中的位置核实成功时，沿 section_fetch 展开所在章节，或沿 window_fetch 读取命中附近原文；跨章节的片段优先看 window_fetch。检查 ancestor_context 的父级条件及有关的相邻章节，再作结论。没有章节的碎片直接读原片段和来源。位置无法核实时，先用 outline_fetch 查看目录或读取完整原文，不把片段当作完整依据。

kb_fetch 默认返回全文；view=outline 查看目录，view=section 读取 section_id，view=window 按 start_line、end_line 读取。返回的读取参数固定了记录版本，可直接沿用。max_chars 控制章节或窗口的正文与父级导语字符预算；truncated 表示仍有内容，沿 next_fetch 继续读取，父级导语的读取入口也可单独展开。精确核实可用 full_fetch 取全文。kb_index 默认处理待索引记录；确需重建现有语义索引时传 rebuild=true。
