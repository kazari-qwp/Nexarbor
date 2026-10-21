# 可选的官方运行端口

本组件默认不启用，development 也不默认选择它。宿主明确安装后，节点仍须用 offered_tools 提供对应引用，模块须具有相应频道才能调用。

- runtime:agent_run 只运行调用节点自己的 Agent，不接受任意节点 ID，持节点锁时拒绝。
- runtime:checkpoint 保存当前网络，可显式请求全量；调用不暴露 Backend 或文件路径。
- runtime:read_text 是只读 UTF-8 文本端口，默认频道 runtime.text；path 相对项目或为绝对路径，roots 可明确配置额外目录。最多读取 1 MiB，返回 text/path。组件通过正常网络 invoke 使用，节点须显式提供该引用，模块仍受频道及可达范围约束。

本能力没有文件写入、进程执行或通用宿主 RPC。应用的固定初始化仍使用网络配置。
