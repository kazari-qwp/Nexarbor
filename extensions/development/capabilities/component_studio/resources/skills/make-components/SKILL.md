---
name: make-components
description: 从效果需求设计、制作或解释可复用的模块与 Agent 工具，涵盖 ctx、接口、配置前端、依赖和验证。
---

# 制作模块与工具

先加载 `nexarbor-basics`。理解当前网络或已有组件时加载 `inspect-network`，优先看用户选中对象。提问时解释设计，用户要求修改时直接在保留历史的工作分支继续。

## 工作路线

1. 用一句话写用户想要的效果，明确触发、输入、结果和失败情形。有接口兼容要求时，列清不能删除的公开入口与配置；验证真实使用方能调用，不只测试自己新写的接口。有当前网络时先观察，再抽象组件。
2. `catalog_modules` 按职责找已有能力。现有模块符合业务模型时用配置或组合完成；不要为复用而扭曲业务，也不用为每个同类地点、角色复制新模块。
3. 确有缺口，编码前读 `nexarbor-basics` 的 `references/lessons/01-local.md`；需要跨节点时读 `references/lessons/02-network.md` 的节点对象接口，再只选当前需要的机制参考与依赖接口。通用能力做可复用组件，应用专有规则允许用小而明确的专用模块，不把无关职责塞进一个配置接口。模块与工具是一份实现：公开操作处理业务，`agent_tools` 声明给 Agent 的入口。
4. 先做正常流程，再补权限、错误、重复执行和必要的并发测试。锁只包住必须原子完成的短过程，不能包住整轮 Agent。
5. `validate` 后按真实日志局部修复，通过且满足需求就交付。用中文说明用途、装配方式、可调参数和限制；保留源码与历史。
6. 强烈建议阅读小镇案例分析，并查看完整案例本身：分析见 `nexarbor-basics` 的 `references/lessons/13-town-evolution.md`；完整初始项目在 `<安装目录>/resources/examples/npc-town/`，加载 `inspect-network` 后用 `project` 路径按需研究；应用模块从该项目的 `nexarbor.json` 定位，不假定核心组件目录提供同名实现。
7. 按需给组件制作前端配置页面，那种没有什么可调整的不要做进去，一些可以通过前端修改达到通用的功能性模块建议制作前端。

## 按问题读资料

使用 `read_skill_reference(skill="make-components", file="路径")`，不必全部通读：

| 当前工作 | 参考 |
|---|---|
| 最小闭环与制作规范 | references/MODULE_GUIDE.md、references/AGENTS.md |
| 项目内的需求文档、清单和输入样本 | project_files 分层列目录及分页读文本；read_file 只读工作副本 |
| 工具声明、依赖、前端入口 | references/lessons/04-tools-ui.md |
| 真实测试夹具、错误与权限测试 | references/lessons/05-tests.md |
| 跨组件消费、存档重开与变换检查 | nexarbor-basics: references/lessons/15-behavior-tests.md |
| 文件、Agent 运行或存档等宿主能力 | catalog_ports；nexarbor-basics 的 references/lessons/14-host-ports.md |
| 在用户网络副本中试装和验证 | inspect-network 的 references/测试环境.md |
| 前端配置页面与宿主桥接 | references/FRONTEND_GUIDE.md |
| 小镇案例分析与完整样板入口 | nexarbor-basics: references/lessons/13-town-evolution.md |

ctx、可达性、信号、锁、上下文与亚节点机制从 `nexarbor-basics` 的对应参考读取。复用配置方案见 nexarbor-basics 的 references/lessons/08-reuse.md。

正确示范：商店用商品表管理售价和回收价，同类商店通过参数复用；采集、时间和存档各自保留清楚的职责。反例：重复实现相同交易流程，或为减少模块数量把人格、地图、时间、记忆塞进一个模块。

规范和依赖参考只读，不改宿主检查来迎合代码。用户只是提问时先解释；明确要求修改时才动手，不擅自改无关内容。

接口不清楚先查对应参考；能力未开放则说明缺口。不要通过故意失败的测试、导入核心内部对象、反射或扫描安装目录试探接口。`read_file` 使用 `list_files` 返回的原始路径；Skill 内的 `references/...` 路径属于 `read_skill_reference`，不要给副本路径再加 references 前缀。

公开 ABI 已给出时直接使用其实际数据结构；不要为猜测的字段名和对象类型增加多套兼容分支。测试同时核对默认入口、同类实例组合和真实消费方。

## Git 和进度

用 `project_git` 查看状态、分页差异和提交历史；需要时提交、配置用户提供的远程地址、推送或恢复。`restore` 会先提交当前进度，再从指定提交建立恢复工作分支，继续使用当前对话。用户要求上传时调用 `push`，不强推。恢复的是制作候选，正式运行网络仍由客户端的应用流程更新。
