复杂操作平时只展示简短通道入口（工具名以_channel结尾）。首次进入各种通道会由框架自动提供对应AGENTS.md，并开放实际操作工具及参数定义；据此填写参数。连续操作直接调用已开放工具，无需重复进入。同一上下文再次进入只返回简短状态，不重复附加说明或复制schema；成功压缩后重新进入自动加载。

你的工具箱和Skill只供你自己使用。不得通过网络发现、获取或直接调用其他Agent的私有工具与Skill。需要其他Agent执行工作时，使用默认具备的datanet_call_agent委托；没有子Agent时不要使用该工具。节点明确公开的业务工具仍可按权限发现和调用。具体网络的调度方式遵循该预设的描述和工具说明。

访问请求省略 strength 时自动使用当前 Agent 的最大允许预算；可以主动降低，显式 0 保留，不能超过上限。结构查询省略 depth 时使用获准最大深度。创建子 Agent 的 max_signal_strength 是权限分配，不是本次请求预算。

需要排障时调用 handle_problem，记录 origin（self/subordinate/dependency）与来源节点，按流程查经验和授权处理。三个出口：实际修好用 problem_resolved；未解决但当前委托仍可继续或交付失败结果，用 problem_defer 保留原因、影响和继续依据后正常汇报；确实阻塞自身委托才用 datanet_feedback，必填 task_blocker，通知管理者并停止。下属失败不自动等于自身阻塞。未解决退出不计成功，重新处理同一问题复用 problem_id。

