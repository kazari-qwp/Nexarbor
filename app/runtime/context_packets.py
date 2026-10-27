"""将组装结果应用到 Agent 的输入表。"""


def apply_context_packet(agent, state, source, packet):
    if not isinstance(packet, dict) or packet.get("format") != "nexarbor-context/v1":
        return False
    agent.update_inputs(source, **packet["patch"])
    state["context_assembly_errors"] = packet.get("errors", [])
    return True
