---
name: make-components
description: 从效果需求设计、制作或解释可复用的模块与 Agent 工具，涵盖 ctx、接口、配置前端、依赖和验证。
---

# 制作模块与工具

先加载 `nexarbor-basics`。理解当前网络或已有组件时加载 `inspect-network`，优先看用户选中对象。提问时解释设计，用户要求修改时直接在保留历史的工作分支继续。

## 工作路线

1. 用一句话写用户想要的效果，明确触发、输入、结果和失败情形。有当前网络时先观察，再抽象组件。
2. `catalog_modules` 按职责找已有能力。能用配置或组合完成就交付配置方案；不用为每个地点、角色或请求造新模块。
3. 确有缺口，先读依赖接口与当前需要的机制参考，设计一个小而完整的通用组件。模块与工具是一份实现：公开操作处理业务，`agent_tools` 声明给 Agent 的入口。
4. 先做正常流程，再补权限、错误、重复执行和必要的并发测试。锁只包住必须原子完成的短过程，不能包住整轮 Agent。
5. `validate` 后按真实日志局部修复，通过且满足需求就交付。用中文说明用途、装配方式、可调参数和限制；保留源码与历史。

## 按问题读资料

使用 `read_skill_reference(skill="make-components", file="路径")`，不必全部通读：

| 当前工作 | 参考 |
|---|---|
| 最小闭环与制作规范 | references/MODULE_GUIDE.md、references/AGENTS.md |
| 工具声明、依赖、前端入口 | references/lessons/04-tools-ui.md |
| 真实测试夹具、错误与权限测试 | references/lessons/05-tests.md |
| 在用户网络副本中试装和验证 | inspect-network 的 references/测试环境.md |
| 配置页面与宿主桥接 | references/FRONTEND_GUIDE.md |

ctx、可达性、信号、锁、上下文与亚节点机制从 `nexarbor-basics` 的对应参考读取。复用配置方案见 nexarbor-basics 的 references/lessons/08-reuse.md。

正确示范：做一个可配置的交易组件，配置商品、价格和扣费字段。反例：为商店、酒馆各写一套硬编码交易逻辑，或把人格、地图、时间、记忆塞进同一个应用级模块。

规范和依赖参考只读，不改宿主检查来迎合代码。用户只是提问时先解释；明确要求修改时才动手，不擅自改无关内容。

## Git 和进度

用 `project_git` 查看状态、分页差异和提交历史；需要时提交、配置用户提供的远程地址、推送或恢复。`restore` 会先提交当前进度，再从指定提交建立恢复工作分支，继续使用当前对话。用户要求上传时调用 `push`，不强推。恢复的是制作候选，正式运行网络仍由客户端的应用流程更新。
