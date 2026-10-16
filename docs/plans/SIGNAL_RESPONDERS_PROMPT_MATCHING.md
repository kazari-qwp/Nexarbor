# 频道响应器与提示词匹配器（2026-10-16）

用户确认：核心信号只携带内容/频道/强度等传播属性，不按节点类型或权限过滤激活。接口频道交集决定通过；节点响应器频道集合交集决定执行。响应器的工具及参数按配置顺序执行，同节点多个响应器有序，不同节点并行；当前层全完成后下一层。匹配器独立于信号，读取扩展元数据，使用文档ID+版本及原生上下文标记按需注入，首次/变更/压缩后补充。NPC身份状态不增加核心字段。

实现边界：核心删除NodeFilter/PermissionRequirement/activation与非等待通知分支，网络格式v5，旧格式直接拒绝。核心保留逐层等待/权限/强度/失败与超时/幂等/回环；不包含业务响应配置。共享capabilities/signal_response组件保存节点响应配置、绑定受授权内部工具，支持字面值和JSON Pointer参数引用。共享capabilities/prompt_matching不导入信号，支持条件文档、版本哈希、原生标记、简短最新状态记录，不重写角色系统提示。NPC使用responses.json串联时钟工具、匹配工具和Agent运行工具；元数据和知识来源由NPC组件提供。专属文档条件化，失配发送最新状态，历史不抹除。

只修改E成品目录。不迁移前两个应用。不运行全世界真实Agent。本次以核心、通用组件、NPC最小场景和真实Harness+Mock/原生文档压缩测试验证，必要时才使用已授权的限额单NPC付费测试。额度5小时剩余低于8%保存并暂停，不使用重置卡。Agent文档/描述原文与地址交付，本地commit。

步骤：1核心升级；2实现两个共享组件；3NPC接线、元数据和条件文档；4最小测试与文档审阅；5提交。每步维护本记录。
用户追加：增加agent_metadata共享功能模块。核心保留原Agent结构；扩展命名空间存静态属性，提供器读取NPC现有业务状态，避免复制两份状态。匹配器通过该模块获取元数据。core命名空间保留；提供器字段与附加字段冲突明确拒绝。

最新更正：使用node_metadata节点元数据扩展器，适用于任意已有节点，不限制Agent。Agent/NPC是使用者，扩展属性仍不写入核心Node/Agent字段。变更事件为node/metadata-changed。

最新要求：所有读方统一调用核心Node.get_metadata/Network.get_metadata/Node.describe。核心MetadataRegistry无扩展时只给标准字段；有扩展自动并入extensions。扩展器只注册提供器，不要求工具适配；匹配器也不再接收专用元数据回调，直接统一读取。Backend恢复和网络拼图挂载保留注册入口。扩展命名空间默认仅自身/根/宿主可读，可声明public；避免node_list自动描述泄露私人状态。

阶段完成：核心v5、共享signal_response/prompt_matching/node_metadata均已接入。统一MetadataRegistry直接服务Node.get_metadata/Network.get_metadata/describe，扩展自动合并且权限统一；Backend启动注册，节点业务通过提供器维护。当前35项联合测试通过，原生Harness+Mock与文档标记测试通过；最后做Backend启动/恢复接线的复核，不调用付费API。Agent文案已汇总到NPC审阅清单。

最终验收：核心20项+共享组件6项+NPC9项，共35项联合测试通过；history_markers_test及真实Harness+Mock通过。匹配器不改角色系统提示，3次NPC请求只加载3份条件文档+1份元数据记录。节点元数据在纯Backend启动时注册，Node.get_metadata/Network.get_metadata/describe/创建摘要统一自动合并；无扩展回标准字段。旧过滤器及非等待分支已移除。无付费API、无整世界运行、未操作用户客户端。准备本地提交，不push或打包。
