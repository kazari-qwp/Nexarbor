# LangGraph 后端

复用官方 `langgraph==1.2.16` Python 包，使用 StateGraph、条件边、显式并行汇合和 ainvoke。只作为可选执行图后端；不接管模型循环、权限网络或持久化。

安装：`python -m pip install -r extensions/foundation/capabilities/langgraph_backend/requirements.txt`。选择 event_trigger/module_execution 会通过组件依赖加载后端；框架不会自动安装 Python 依赖。

官方接口：[安装](https://docs.langchain.com/oss/python/langgraph/install)、[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)。不需要 LangGraph Server、云服务或新 API Key。本项目没有复制或修改上游源码。

组件 manifest 的 python.collect/python.metadata 供 Windows 构建脚本收集第三方模块与分发元数据。执行图仅使用调用期内存状态，不启用 LangGraph checkpointer；长期状态和 Harness 上下文继续由核心提交点统一恢复。

完整配置见 [执行图接口](../../../../docs/EVENT_EXECUTION.md)。
