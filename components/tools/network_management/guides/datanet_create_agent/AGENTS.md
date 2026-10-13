# 创建 Agent 节点
用 child_id 创建下属 Agent 节点；parent_node_id 省略表示自己。个人 Markdown 记忆和读写工具会自动配备。
preset 省略使用 worker；toolboxes 省略使用预设配置。operator 预设自带官方文件和终端工具。
prompt 可填写获准的自定义职责；max_signal_strength 省略使用预设值，不超过创建者上限。
配置匹配时，框架复用当前根网络池里的 Agent，保留其会话和个人记忆。使用返回的实际 node_id。
