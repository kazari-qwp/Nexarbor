# LlamaIndexNode

项目当前唯一的文档检索节点，原自制向量节点和双节点检索网络已移除。
LlamaIndex 负责文件读取、SentenceSplitter 分块、嵌入调度、VectorStoreIndex、
默认文档/向量存储的持久化和检索；本类只适配 DataNet 接口。
节点只返回原文片段、相关性和来源；答案由外部 Agent 生成，节点不配置生成模型。

安装依赖：`python -m pip install -r datanet/components/nodes/llamaindex_node/requirements.txt`。

`read({"method":"semantic","query":"...","top_k":3})` 返回 NodeResult；
`ingest(input_files)` 全量建立新索引，`load()` 加载已有索引。
这些能力也已登记为节点工具：

```python
node.invoke_tool("build_index", input_files=["E:/documents/example.txt"],
                 chunk_size=512, chunk_overlap=64)  # 写工具：全量替换当前索引
node.invoke_tool("load_index")  # 只读工具：重新加载磁盘索引
stats = node.invoke_tool("update_documents", input_files=["E:/documents/new.txt"])  # 写工具：增量更新
result = node.invoke_tool("search", query="文档讲了什么？", top_k=3)  # 只读，返回NodeResult
```

查询也可以继续走统一 `read()`；首次查询自动加载已有索引。
`update_documents` 返回 added、updated、skipped 数量；新文档追加，同ID内容未变则跳过，变化则替换该文档。
ID使用规范化绝对路径（分页读取器可能带part编号），哈希使用解析内容及稳定的路径/文件名元数据；
文件改名或移动视为新文档，不做跨路径内容去重。未传入的其他文档保留，不自动同步删除。
分块参数随索引保存并在加载时恢复。此前随机ID建立的索引需要明确全量重建一次，才能按路径增量更新。
尚未封装删除工具。
加载索引必须使用与建库匹配的嵌入模型。网络JSON已支持llamaindex类型。

官方文本示例：
https://developers.llamaindex.ai/python/framework/getting_started/starter_example/

复测：`python -m datanet.components.nodes.llamaindex_node.demo`。
示例只使用已有本地 BGE-M3（CPU），不需要 Ollama 或生成模型；
下载官方 Paul Graham 文本，建立并重新加载索引，测试中英文问题。
文本、索引和检索报告 `retrieval_report.json` 放在 `.models/research/llamaindex_starter/`，不上传。
NLTK_DATA、TIKTOKEN_CACHE_DIR、HF_HOME 应指向 E 盘缓存；首次运行需下载分词资源。
没有默认重排，也不调用 OpenAI 云端模型。


## 配置与版本提交

保存网络需要显式embedding_config，模型对象本身不写入JSON。配置示例：

```python
node = LlamaIndexNode("rag", "资料", "E:/data/index", embedding_config={
    "model_path": "E:/models/bge-m3", "device": "cpu",
    "max_length": 1024, "batch_size": 2,
})
```

JSON节点类型为llamaindex，参数为storage_path和embedding（上述配置）。路径相对网络配置保存，HuggingFaceEmbedding在首次使用时才初始化。

实例内RLock与目录旁的FileLock协调读写。同一索引目录的不同实例/进程共享文件锁，等待上限60秒。查询会检查当前版本以刷新缓存。增量写入从已提交版本加载独立副本，仅计算新增或变化文档；保存到新版本目录并重新加载校验后原子替换current.json。全量重建也先准备独立候选。保存或切换失败不发布候选版本。

存储布局是current.json和versions/<版本号>/，分块参数随版本保存。旧版本与未提交目录暂留，不自动清理；不保证断电或硬件损坏恢复。此前直接保存在根目录的试验索引需要重建一次，不保留旧格式兼容包装。
