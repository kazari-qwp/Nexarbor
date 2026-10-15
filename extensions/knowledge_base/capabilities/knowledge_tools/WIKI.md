# Wiki 操作映射

后附 llm-wiki 的原版操作指南。此应用已固定工作方式，按以下映射使用已装配的工具：

- 集合的 description、schema 与 tags 是本库的用途和约定，无需重新询问空库布局。资料是否可保存以当前任务授权为准。
- sources 是不可修改的原始资料和版本记录；用 kb_intake、kb_fetch 读取，保留来源引用。
- wiki 页面通过 kb_store、kb_update、kb_delete 管理；页面内容可包含 YAML frontmatter 与 [[wikilinks]]。链接目标用记录 ID 或稳定 key。
- llm-wiki search 映射为 kb_wiki(action=search)，graph 映射为 kb_wiki(action=lint)。lint 返回结构检查和过期来源，语义矛盾仍需你检查。
- wiki-log 与 sync 的追溯、版本及索引工作由知识存储的写入流程处理，无需调用额外 CLI 或修改文件。
- query 中的知识回写仍需当前任务的写入权限；只读任务只返回结果。原版指南中的联网 research 不在本组件内。

先读取已有页面再合并；矛盾并列注明来源。检查发现过期页面时，核对来源后更新，不要凭猜测修正。交付中注明仍未解决的问题。
