"""身份隔离的私人记忆；不会主动填进任何上下文。"""
from datanet.core.module_protocol import ComponentResult
from datanet.core.json_values import thaw as _plain
def _error(message): return ComponentResult(status='error', error=message)
def _memory_result(memories, duplicate=False): return {'duplicate': duplicate, 'memories': _plain(memories), 'count': len(memories)}
async def execute(ctx, activation):
    if ctx.requester_id != ctx.node_id: return _error('只能操作自己的私人记忆')
    operation, parameters = activation.operation, activation.parameters or {}
    if operation == "remember":
        text = parameters.get("text")
        key = parameters.get("key")
        memories = [dict(item) for item in ctx.state.get("memories", []) if isinstance(item, dict)]
        if key is not None:
            for item in memories:
                if item.get("key") == key:
                    if item.get("text") == text:
                        return ComponentResult(data=_memory_result(memories, duplicate=True))
                    return _error("相同记忆键已经记录了不同内容，不能覆盖")
        entry = {"text": text}
        if key is not None:
            entry["key"] = key
        memories.append(entry)
        limit = ctx.config.get("max_memories", 100)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            limit = 100
        if len(memories) > limit:
            memories = memories[-limit:]
        ctx.state["memories"] = memories
        return ComponentResult(data=_memory_result(memories))

    if operation == "recall":
        query = parameters.get("query") or ""
        needle = str(query).casefold()
        memories = []
        for item in ctx.state.get("memories", []):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", ""))
            if not needle or needle in text.casefold():
                memories.append(dict(item))
        return ComponentResult(
            data={"query": str(query), "memories": _plain(memories), "count": len(memories)}
        )

    return _error("不支持的操作")
