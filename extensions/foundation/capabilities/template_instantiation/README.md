# 官方声明模板实例化

默认不启用。应用配置必须明确安装本扩展，并由宿主登记固定模板、可调用的节点编号、输入 Schema、固定的连接锚点。节点还须 offered_tools 提供 templates:instantiate，组件须拥有该频道。

调用只接受 template/key/arguments，不接受源码、文件路径、工具名称或原始网络 JSON。宿主只实例化已登记的声明模板；替换位置限于名称、说明和组件配置。连接到现有网络的位置在模板中预先声明。请求键幂等；失败恢复本次新节点和旧出边。模板不复用已有 Agent 会话或记忆文件。

bindings 每项由 path（目标 JSON Pointer）和 input（输入字段名或 JSON Pointer，例如 /parents/0）组成，只复制已经过 arguments_schema 校验的值，没有可执行表达式。

这是明确的官方特殊能力，不属于普通模块的局部 API。用于出生、创建固定任务卡等需要新节点的流程；不提供自主修改整个网络的根 Agent。
