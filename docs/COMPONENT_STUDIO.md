# 客户端组件工作室

工作台现在可以查看组件源码、建立修改副本、手工编辑，或把需求交给 DeepSeek Harness 的组件制作 Agent。验证、反馈修复、发布和挂载使用同一条流程。

## 使用

1. 启动 Nexarbor 桌面工作台，打开“组件工作室”。已发布组件可以直接查看源码；修改前点击“建立修改副本”。
2. 新组件选择“从空白制作组件”。填写功能、挂载节点类型、配置和预期结果。首次需求可以详细说明，再逐渐尝试简短表达。
3. “连接 Harness”使用已运行客户端的原生会话、模型配置和编码工具。模型会话也出现在 Harness 左侧列表。密钥保留在宿主配置中。
4. 点击“交给 Agent 制作”。Agent 写完后，宿主执行固定契约检查和组件测试；失败日志自动交回同一会话，最多自动修复两轮。支持停止制作和停止验证。
5. 验证通过后发布。发布内容与测试时的源码摘要必须相同；再修改源码需要重新验证。已发布版本只读。
6. 选择目标节点，填写 Schema 生成的配置表单，装配组件。运行中的网络需先完成当前信号，才能更换组件。
7. 顶部“网络文档”可以新增和编辑人格、地图、常识等文本，修改进入草稿，应用网络后生效。Agent 的属性面板提供通用执行设置，可启用 Harness 并配置访问强度、期限和请求前的 prepare 操作。

“继续原会话”和“从当前历史分叉”复用同一工作副本的制作历史。工作指南前缀变化时需要新会话。分叉的 token 统计扣除继承历史，避免重复计算。

## 标准模块

组件提供 `module.json`、`module.py`、`example.json`，并可附带 README 和 tests。契约包含身份和版本、依赖、支持的节点类型、配置与状态 Schema、公开工具、信号频道及内部 operations。

- `setup()` 初始化缺失状态；`on_signal(context)` 可同步或异步处理信号。
- 工具声明自己的频道。框架检查频道路径和强度；可信调用者由宿主提供，不让模型填写身份。
- `backend.modules.call()` 调用声明的组件操作。短事务可回滚选定组件的状态。
- `nodeModule` 描述符允许直接加载标准模块，不必为每个组件写注册代码。
- `backend.execute_agent()` 是宿主适配端口；业务组件不实现自己的模型循环。

完整接口见 [MODULE_GUIDE.md](../extensions/development/capabilities/component_studio/resources/MODULE_GUIDE.md)。客户端的代码编辑与差异视图复用 CodeMirror。当前 Python 模块由本地 Python 子进程验证和运行，不需要客户端内置通用编译器；验证子进程有时间和输出上限，不能把它等同于安全沙箱。

## 小镇预设

`configs/npc_town/network.json` 包含完整网络和文档配置；`extensions/generated_town` 保存 Agent 产物。小镇的业务代码没有加入核心，宿主也没有逐组件适配分支。

开发环境的桌面启动参数：

```text
Nexarbor Workbench.exe --workspace <运行目录> --network <configs/npc_town/network.json 的绝对路径>
```

只在空运行目录应用初始配置；已有存档优先。工作台也可以从“NPC小镇 · Agent制作组件”网络预设载入草稿，校验后应用。配置附带的人格、常识、地图与节点记忆一起进入持久化记录。

通用批量制作入口为 `scripts/studio_make_components.mjs`；`scripts/studio_export_library.py` 原样导出验证后的组件，额外生成声明式描述符和来源摘要。

[实测报告](applications/npc_world/COMPONENT_STUDIO_TEST_20261018.md)记录了制作边界、一天真实运行、出生与恢复测试；[输入原文](applications/npc_world/COMPONENT_PROMPTS_20261018.md)和[Agent 文本原文](applications/npc_world/AGENT_TEXTS_20261018.md)可供核对。
