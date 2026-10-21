# 调用宿主能力

`catalog_ports` 查询当前宿主实际提供的能力；默认只列职责，精确 ref 展开参数与已声明的 result_contract。端口不是 ctx 的隐式特权，节点须在 offered_tools 中提供 ref/channels，模块须具备对应频道，再通过正常的 `ctx.network.invoke(target,ref,args,channels=[...])` 调用。

runtime_ports 安装后提供以下能力。普通空项目不默认启用；当前小镇在 networks/main.json 的 runtime.components 中显式启用它，制作测试副本按项目运行时声明加载。先用 catalog_ports 确认当前环境，节点仍须显式提供和授权：

| 引用 | 通常使用的频道 | 行为 |
|---|---|---|
| runtime:agent_run | runtime.agent | 运行调用节点自己的 Agent；持事务锁时拒绝 |
| runtime:checkpoint | runtime.checkpoint | 保存网络与检查点，可 full:true |
| runtime:read_text | runtime.text | UTF-8 只读文本，参数 path、可选 roots，返回 text/path，最多 1 MiB |

例如读取文件：节点声明 `offered_tools:[{ref:'runtime:read_text',channels:['runtime.text']}]`，模块授权 runtime.text，再 `await ctx.network.invoke(ctx.node_id,'runtime:read_text',{'path':'资料/说明.md'},channels=['runtime.text'])`。路径相对项目；外部目录用 roots 明确配置。这里返回端口的业务值，不额外套 ComponentResult。

官方 Harness 工具返回 SDK envelope：`isError/content/meta/value`。成功的业务结果在 `value` 中，具体字段查该端口的 `result_contract.value_schema`；例如终端的输出为 `value.stdout.text`。不要猜字段或把端口结果当普通字符串。`runtime:agent_run` 只运行调用者自身；向另一个节点 invoke 它不会把调用者变成目标节点。跨角色调度须沿图触发对方的本地执行模块。

项目内 UTF-8 文本可优先用 `runtime:read_text` 的项目相对路径，便于整体移动。官方文件／终端工具的工作目录由工具宿主决定，不能假设等于项目目录；制作时 `project_files` 回执的 project 给出实际项目根目录，按精确工具契约提供路径或 workdir。

ModuleHarness 的 `h.register_readonly_ports()` 登记同一份真实只读文本实现；测试节点仍需配置 offered_tools，模块仍须授权。`h.folder` 是该夹具的项目目录，测试可在里面建立实际文件，检验路径、编码与大小错误。模型和其他外部副作用没有因此开放。

test_environment 只允许读取隔离副本内的文本，禁用其他真实外部工具、模型与项目外 roots。缺失的外部材料要报告，不能偷偷读取正式项目。端口不存在时报告能力缺口，不猜扩展入口，也不直接拿 Backend、文件句柄或进程替代。
