"""同步 Agent 委托：独立任务会话、显式许可及调用链保护。"""

from contextvars import ContextVar

from datanet.nodes import NodeResult
from datanet.tool_access import reachable


call_chain = ContextVar("agent_call_chain", default=())
request_budget = ContextVar("agent_request_budget", default=None)
MAX_DEPTH = 4
MAX_DELEGATIONS = 8


def ask_agent(network, owner, target_node_id, message, scope="integrated"):
    if not isinstance(target_node_id, str) or not isinstance(message, str) or not message.strip():
        raise TypeError("目标必须为字符串，委托消息必须为非空字符串")
    if target_node_id not in network.delegation_permissions.get(owner.node_id, []):
        return NodeResult(status="forbidden", errors=["当前节点没有向目标委托的许可"])
    target = network.nodes.get(target_node_id)
    if target is None or target.agent is None:
        return NodeResult(status="not_found", errors=["目标不存在或没有 Agent"])
    paths = {node.node_id: path for node, path in reachable(network, owner.node_id, scope)}
    if target_node_id not in paths:
        return NodeResult(status="forbidden", errors=["目标不在当前节点读取可达范围内"])
    chain = call_chain.get() or (owner.node_id,)
    if chain[-1] != owner.node_id:
        return NodeResult(status="forbidden", errors=["委托工具所属节点与当前调用者不一致"])
    if target_node_id in chain:
        return NodeResult(status="error", errors=["拒绝循环 Agent 调用"])
    if len(chain) >= MAX_DEPTH:
        return NodeResult(status="error", errors=["达到 Agent 调用深度上限"])
    budget = request_budget.get()
    if budget is None:
        budget = {"calls": 0}
    if budget["calls"] >= MAX_DELEGATIONS:
        return NodeResult(status="error", errors=["达到本任务 Agent 委托次数上限"])
    budget["calls"] += 1
    chain_token = call_chain.set(chain)
    budget_token = request_budget.set(budget)
    try:
        reply = target.agent.run(message, node=target, isolated=True)
        return NodeResult(items=[{"target_node_id": target_node_id, "reply": reply}], sources=[{
            "node_id": target_node_id, "delegation_path": paths[target_node_id],
            "call_chain": [*chain, target_node_id],
        }])
    except Exception as error:
        return NodeResult(status="error", errors=[str(error)])
    finally:
        request_budget.reset(budget_token)
        call_chain.reset(chain_token)


def attach_delegation_tool(network, owner):
    owner.tools["ask_agent"] = lambda target_node_id, message, scope="integrated": ask_agent(
        network, owner, target_node_id, message, scope)
    return {"type": "function", "function": {"name": "ask_agent",
        "description": "从当前所属节点向获准且可达的目标 Agent 委托任务，使用目标自身职责与独立会话。可能执行目标工具，不是只读工具。",
        "parameters": {"type": "object", "properties": {
            "target_node_id": {"type": "string"}, "message": {"type": "string"},
            "scope": {"type": "string", "enum": ["local", "integrated", "federated"]}},
            "required": ["target_node_id", "message"], "additionalProperties": False}}}
