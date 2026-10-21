# 查找知识

先用 kb_catalog 找到相关集合。Wiki 和 RAG 都用 kb_search 找入口；semantic=true 进行语义检索，entry 提供固定版本和读取参数。已知入口直接读取。字段筛选需要指定 CSV 或 SQLite 集合，SQLite 的排序和分组统计使用 kb_query。

kb_query 仅用于 SQLite。计数用 aggregate={"function":"count"}；求和、平均值、最小值、最大值还须在 aggregate 内填写 field，fields 只选择返回列。CSV 的条件筛选用 kb_search 的 filters。

检索片段用于找到入口，不代表文档的完整结论。命中返回 section_fetch、window_fetch 时，可直接将参数交给 kb_fetch，分别展开所在章节或命中附近原文；片段跨章节时优先看窗口。检查 ancestor_context 中的父级条件，并按需查看相邻章节。没有章节的独立碎片直接读取自身和来源。位置无法核实时，使用 outline_fetch 或完整原文核对。

Wiki 页面可包含同集合关联链接，沿返回的 read 参数访问；view=links 按需查看全部关联，links_next_fetch 读取下一页。锚点链接先查看目标目录；unresolved 或 ambiguous 要核对目标，不能猜测。链接不授予额外权限，也不等于来源。历史页面链接指向读取时的目标当前版，返回参数将该版固定；历史依据仍按 sources 的版本读取。

kb_fetch 默认读取全文；view=outline 查看目录，view=section 按 section_id 读取，view=window 按 start_line、end_line 读取。按返回的参数导航会固定记录版本。max_chars 限制正文与父级导语字符预算；有 truncated 或 next_fetch 时尚未读完，按返回的入口继续。父级导语被截断时也有独立读取入口；full_fetch 可取完整原文。引用记录 ID、版本与实际位置。Wiki 的 sources 指向原始资料；needs_refresh 表示来源已变化。需要完整导入原件时查看 origins 中的归档路径。

语义索引未就绪时可以继续关键词查询。没有找到资料时说明检索范围和缺失内容。
