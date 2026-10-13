# TextFileNode

一个节点绑定一个UTF-8文本文件，适用于Markdown记忆、笔记或普通文本。
文件路径由装配者指定；工具不接受其他目标路径。

```python
from datanet.components.nodes import TextFileNode
node = TextFileNode("memory", "个人记忆", "text", "E:/data/memory.md")
node.invoke_tool("write", key="content", value="# 记忆\n", mode="insert")
node.invoke_tool("write", key="content", value="用户喜欢中文。\n", mode="append")
result = node.read({"method": "key", "key": "content"})
print(result.items[0]["content"])
```

主键固定为`content`，读取返回全文与来源；缺失文件返回not_found，读取失败返回error。
写入模式：insert仅创建，update仅替换已有文件，upsert创建或替换，append原样追加（不存在则创建，不补换行）。
read工具只读，write工具需写权限；网络write同样支持append。
覆盖或追加前将原文件字节保存为同目录`文件名.bak`，仅保留上一版。
文件通过同目录临时文件替换，实例内读写加锁；不支持跨进程并发写。
网络JSON使用`type: text_file`、`parameters: {file_path: ...}`，只保存路径，不把正文塞入配置。
