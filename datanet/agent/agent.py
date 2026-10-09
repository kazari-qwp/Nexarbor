"""节点持有的 Agent；模型客户端与业务配置由外部提供。"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any
from pathlib import Path
from threading import Lock, get_ident

if TYPE_CHECKING:
    from datanet.nodes.node import Node


class Agent:
    def __init__(self, client: Any, model: str, prompt_path: str | Path,
                 tool_definitions: list[dict], max_rounds: int = 5,
                 max_tokens: int = 1000, extra_body: dict | None = None):
        if not isinstance(max_rounds, int) or isinstance(max_rounds, bool) or max_rounds < 1:
            raise ValueError("max_rounds 必须是正整数")
        self.client = client
        self.model = model
        self.prompt_path = Path(prompt_path).resolve()
        self.system_prompt = self.prompt_path.read_text(encoding="utf-8")
        if not self.system_prompt.strip():
            raise ValueError("系统提示词文件不能为空")
        self.tool_definitions = deepcopy(tool_definitions)
        self.max_rounds = max_rounds
        self.max_tokens = max_tokens
        self.extra_body = deepcopy(extra_body)
        self._lifecycle_lock = Lock()
        self._running_thread = None
        self.reset()

    def rebuild(self) -> Agent:
        """重新加载文件；保留客户端和配置，创建全新会话实例。"""
        return Agent(self.client, self.model, self.prompt_path, self.tool_definitions,
                     self.max_rounds, self.max_tokens, self.extra_body)

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def run(self, user_message: str, *, node: Node, isolated: bool = False) -> str:
        from datanet.agent.delegation import call_chain, request_budget
        chain = call_chain.get()
        if node.node_id in chain:
            raise RuntimeError("拒绝循环 Agent 调用")
        chain_token = call_chain.set((*chain, node.node_id))
        budget_token = request_budget.set({"calls": 0}) if not chain else None
        acquired = False
        try:
            acquired = self._lifecycle_lock.acquire(blocking=not isolated)
            if not acquired:
                raise RuntimeError("目标 Agent 正忙，请稍后重试")
            self._running_thread = get_ident()
            try:
                return self._run(user_message, node=node, isolated=isolated)
            finally:
                self._running_thread = None
        finally:
            if acquired:
                self._lifecycle_lock.release()
            call_chain.reset(chain_token)
            if budget_token is not None:
                request_budget.reset(budget_token)

    def _run(self, user_message: str, *, node: Node, isolated: bool = False) -> str:
        if not isinstance(user_message, str):
            raise TypeError("用户消息必须是字符串")
        if node.agent is not self:
            raise RuntimeError("Agent 必须绑定到当前节点")
        tool_names = {tool["function"]["name"] for tool in self.tool_definitions}
        missing = tool_names - node.tools.keys()
        if missing:
            raise ValueError(f"工具定义未在节点注册：{sorted(missing)}")

        # 成功完成后才提交历史，失败不保留不完整的工具对话。
        messages = [{"role": "system", "content": self.system_prompt}] if isolated else deepcopy(self.messages)
        messages.append({"role": "user", "content": user_message})
        for _ in range(self.max_rounds):
            request = {
                "model": self.model,
                "messages": deepcopy(messages),
                "max_tokens": self.max_tokens,
            }
            if self.tool_definitions:
                request.update(tools=deepcopy(self.tool_definitions), tool_choice="auto")
            if self.extra_body is not None:
                request["extra_body"] = deepcopy(self.extra_body)
            response = self.client.chat.completions.create(**request)
            if not response.choices:
                raise RuntimeError("模型返回了空 choices")
            choice = response.choices[0]
            if choice.finish_reason == "length":
                raise RuntimeError("模型输出被 token 上限截断")
            message = choice.message
            if not message.tool_calls:
                if not message.content or not message.content.strip():
                    raise RuntimeError("模型没有返回正文或工具调用")
                messages.append(message.model_dump(exclude_none=True))
                if not isolated:
                    self.messages = messages
                return message.content

            messages.append(message.model_dump(exclude_none=True))
            for tool_call in message.tool_calls:
                try:
                    name = tool_call.function.name
                    if name not in tool_names:
                        raise ValueError(f"工具未向模型开放：{name}")
                    arguments = json.loads(tool_call.function.arguments)
                    if not isinstance(arguments, dict):
                        raise TypeError("工具参数必须是字典")
                    result = node.invoke_tool(name, **arguments)
                    if is_dataclass(result) and not isinstance(result, type):
                        result = asdict(result)
                    content = json.dumps(result, ensure_ascii=False, allow_nan=False)
                except (ValueError, KeyError, TypeError) as error:
                    content = json.dumps({"error": str(error)}, ensure_ascii=False)
                messages.append({
                    "role": "tool", "tool_call_id": tool_call.id, "content": content,
                })
        raise RuntimeError(f"模型请求达到 {self.max_rounds} 轮，尚未得到最终回复")
