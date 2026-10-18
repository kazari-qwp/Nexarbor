# 移动到此：三节点演示

用客户端“导入”打开同目录的 `network.json`，再点击“应用网络”。它是完整的 v8 `{network, files}` 网络文件，不含额外应用代码、原生会话或密钥。

初始状态：阿林（root）在广场（square）；广场与杂货店（shop）有双向道路。两个地点都装了“移动到此”和“位置资料”，NPC 装了“位置资料”。地点的模块访问强度为 2，频道为 movement、tools。道路与位置边的门槛为 1，倍率为 1；边的 relation 属性分别为 road、location。

在阿林的 Agent 会话中要求“去杂货店”。Agent 先用内置 network_visit 访问 shop，取得它提供的“移动到此”，再无参数调用该工具。移动对象由核心绑定的请求者身份确定，不从参数接收 NPC 编号。也可以先访问挂有工具收集器的节点，经收集器转调取得该工具。

成功后阿林的双向位置边连接到杂货店，广场访客为空，杂货店访客包含 root；位置资料的 location 和 Agent 当前地点说明一起更新。广场与杂货店之间的道路不变。反向前往广场采用同样操作。固定顺序由模块中的 await 表达；锁定三个节点，保证其他请求不会读到半途状态，出错则回滚。

这里未配置“模块流程执行器”，也不需要 LangGraph。演示的结构、实际工具取得与执行、并发和回滚有自动测试；自动验收没有调用付费模型。人工打开 Agent 会话后使用用户配置的 Harness 模型。

模块实现见 [移动到此](../../extensions/foundation/capabilities/move_here/module.py)，资料模块见 [位置资料](../../extensions/foundation/capabilities/place_info/README.md)。
