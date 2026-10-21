# knowledge.catalog

历史 KnowledgeStore 的目录、入库、版本与来源索引。每个集合通过宿主普通模板产生真实 knowledge.collection 节点，目录持久保存集合到节点的引用。跨集合检索沿用原来的关键词/向量融合排名，只搜索本次频道访问得到的集合；读取正文仍通过集合节点。实现来源：历史提交756763f。原文、版本和素材文件位于项目workspace/knowledge；不是临时运行目录。

操作与参数见module.json，业务实现见module.py。
