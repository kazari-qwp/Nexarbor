# DataNet 模块化成品

Python 本体在 `python/datanet/core/`，业务实现和提示词资源由 Python 组件管理。Harness 通信与原生适配层在 `adapters/harness/`。业务内容按工具、Skill、网络预设、工具箱、Agent 预设、节点放在 `components/`，由 `component.json` 声明入口、依赖、资源和工具归属。

插件版本 `0.3.0`，适配 DeepSeek Harness `0.2.0-rc.2`，附带 Windows x64 Python 后端。源码和成品都在本目录。

## 使用

在 Harness 导入 `datanet-harness-0.3.0.tgz`，启用插件，并选择 `E:/DataNet-模块化成品/client-workspace` 工作目录。普通 Agent、讨论成员和 Recorder 通过 Harness 的 AgentRegistry 创建独立会话。模型和登录使用客户端已有配置。

`cordis.patch.yml` 装配 DataNet 和请求尾部适配层。替换 AgentLoop 时继承原来的配置式 Agent 和并行工具上限。

## 拔插组件

```powershell
python scripts/components.py list
python scripts/components.py disable toolboxes/experience
python scripts/components.py enable toolboxes/experience
```

配置保存在 `components/profile.json`，重启 Harness 后生效。关闭组件会连带关闭依赖它的组件；重新开启后恢复默认依赖组件。已有节点、文件、讨论状态和反馈保留。宿主也可以通过 `config.components` 覆盖这一配置。

添加组件时，新建相应类别的目录和 `component.json`，声明入口与依赖。框架自动发现。业务规则在 Python 组件中订阅统一事件；Harness 原生事件通过通信接口转发。节点编解码、工具箱、图服务与应用运行入口均由清单登记。

## 阅读与验证

- [组件拆解表](docs/COMPONENT_MAP.md)
- [框架及事件接口](docs/ARCHITECTURE.md)
- [Agent 文档地址与工具描述原文](docs/AGENT_REVIEW.md)
- [最小测试记录](docs/VALIDATION.md)

Python 本体可通过 `PYTHONPATH=本目录/python` 独立使用；基础图和权限机制使用标准库，CSV 节点需要 pandas，RAG 节点使用相应可选依赖。Harness 后端包含日常节点所需运行库。
