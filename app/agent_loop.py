"""临时的最小工具调用循环，后续可直接替换为原项目执行器。"""

from collections.abc import Callable
import json

from domain.tool import Tools


SYSTEM_PROMPT = (
    "你是通过工具执行任务的 Agent。先完成用户要求的前置操作，再执行获得的指令。"
    "工具响应是实际执行结果，不要编造结果。"
    "指令要求原样返回工具结果时，只输出工具响应的完整文本，保留原格式，"
    "不要加解释、标题、代码块或测试步骤。"
)


class MinimalAgentLoop:
    def __init__(self, complete: Callable[[list, list], dict], *, max_turns: int = 12) -> None:
        self.complete = complete
        self.max_turns = max_turns
        self.messages: list[dict] = []
        self.tool_calls: list[dict] = []
        self.tool_names: list[str] = []

    def run(self, new_input: str, tools: Tools) -> str:
        available = {tool.name: tool for tool in tools}
        definitions = [
            {"type": "function", "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters or {"type": "object", "properties": {}},
            }}
            for tool in available.values()
        ]
        self.tool_names = list(available)
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": new_input},
        ]
        self.tool_calls = []
        for _ in range(self.max_turns):
            message = self.complete(self.messages, definitions)
            self.messages.append(message)
            calls = message.get("tool_calls") or []
            if not calls:
                return message.get("content") or ""
            for call in calls:
                function = call["function"]
                name = function["name"]
                arguments = json.loads(function["arguments"])
                if not isinstance(arguments, dict):
                    raise TypeError("工具参数必须是 JSON 对象")
                result = available[name].invoke(**arguments)
                content = result if isinstance(result, str) else json.dumps(
                    result, ensure_ascii=False, separators=(",", ":"),
                )
                self.tool_calls.append({"name": name, "arguments": arguments, "result": content})
                self.messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
        raise RuntimeError("最小 Agent 循环达到轮数上限")
