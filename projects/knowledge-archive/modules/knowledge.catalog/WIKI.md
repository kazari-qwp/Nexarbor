# Wiki 操作映射

后附 llm-wiki 的原版操作指南。此应用已固定工作方式，按以下映射使用已装配的工具：

- 集合的 description、schema 与 tags 是本库的用途和约定，无需重新询问空库布局。资料是否可保存以当前任务授权为准。
- sources 是不可修改的原始资料和版本记录；用 kb_intake、kb_fetch 读取，保留来源引用。
- wiki 页面通过 kb_store、kb_update、kb_delete 管理；完整原文和无结构碎片都可保存为页面，不必强制改写。内容可包含 YAML frontmatter 与 [[wikilinks]]；目标用同集合的记录 ID 或稳定 key。关联链接和来源引用分别维护，不将关联当作事实依据。
- 日常搜索统一用 kb_search，semantic=true 使用页面正文向量找入口；沿 entry 或页面链接的 read 参数继续阅读。view=links 可分页查看关联，歧义或断链要先核对目标。llm-wiki 的 BM25 搜索仍可用 kb_wiki(action=search)；graph 映射为 kb_wiki(action=lint)。lint 返回结构检查和过期来源，语义矛盾仍需你检查。
- wiki-log 与 sync 的追溯、版本及索引工作由知识存储的写入流程处理，无需调用额外 CLI 或修改文件。
- query 中的知识回写仍需当前任务的写入权限；只读任务只返回结果。原版指南中的联网 research 不在本组件内。

先读取已有页面再合并；矛盾并列注明来源。检查发现过期页面时，核对来源后更新，不要凭猜测修正。交付中注明仍未解决的问题。
