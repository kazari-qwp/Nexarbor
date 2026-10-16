"""节点持有的 Agent；模型客户端与业务配置由外部提供。"""
from __future__ import annotations
import json
import re
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any
from pathlib import Path
from threading import Lock, get_ident, Event
from queue import SimpleQueue
import time
from datanet.core.execution_context import task_completion
if TYPE_CHECKING:
    from datanet.core.node import Node

class Agent:

    def __init__(self, client: Any, model: str, prompt_path: str | Path, tool_definitions: list[dict], max_rounds: int=5, max_tokens: int=1000, extra_body: dict | None=None, *, node_bindings: dict[str, str] | None=None, max_signal_strength: float=0):
        from datanet.core.interface import validate_strength
        self.max_signal_strength = validate_strength(max_signal_strength)
        if not isinstance(max_rounds, int) or isinstance(max_rounds, bool) or max_rounds < 1:
            raise ValueError('max_rounds 必须是正整数')
        self.client = client
        self.model = model
        self.prompt_path = Path(prompt_path).resolve()
        self.node_bindings = deepcopy(node_bindings or {})
        prompt = self.prompt_path.read_text(encoding='utf-8')

        def substitute(match):
            alias = match.group(1)
            if alias not in self.node_bindings:
                raise ValueError(f'提示词引用了未绑定的节点：{alias}')
            return self.node_bindings[alias]
        self.system_prompt = re.sub('\\{\\{node:([^{}]+)\\}\\}', substitute, prompt)
        if not self.system_prompt.strip():
            raise ValueError('系统提示词文件不能为空')
        self.tool_definitions = deepcopy(tool_definitions)
        self.max_rounds = max_rounds
        self.max_tokens = max_tokens
        self.extra_body = deepcopy(extra_body)
        self._lifecycle_lock = Lock()
        self._running_thread = None
        self.cancel_event=Event()
        self.inbox=SimpleQueue()
        self.timeout_seconds=60
        self.steps=0
        self.request_tail=[]
        self.reset()

    def rebuild(self) -> Agent:
        """重新加载文件；保留客户端和配置，创建全新会话实例。"""
        return Agent(self.client, self.model, self.prompt_path, self.tool_definitions, self.max_rounds, self.max_tokens, self.extra_body, node_bindings=self.node_bindings, max_signal_strength=self.max_signal_strength)

    def reset(self) -> None:
        self.messages = [{'role': 'system', 'content': self.system_prompt}]

    def run(self, user_message: str, *, node: Node, isolated: bool=False) -> str:
        from datanet.core.access_budget import active_agent
        from datanet.core.execution_context import call_chain, request_budget
        chain = call_chain.get()
        if node.node_id in chain:
            raise RuntimeError('拒绝循环 Agent 调用')
        chain_token = call_chain.set((*chain, node.node_id))
        budget_token = request_budget.set({'calls': 0}) if not chain else None
        agent_token = active_agent.set((self, node.node_id))
        acquired = False
        self.deadline=time.monotonic()+self.timeout_seconds
        try:
            acquired = self._lifecycle_lock.acquire(blocking=not isolated)
            if not acquired:
                raise RuntimeError('目标 Agent 正忙，请稍后重试')
            self._running_thread = get_ident()
            try:
                return self._run(user_message, node=node, isolated=isolated)
            finally:
                self._running_thread = None
        finally:
            if acquired:
                self._lifecycle_lock.release()
            call_chain.reset(chain_token)
            active_agent.reset(agent_token)
            if budget_token is not None:
                request_budget.reset(budget_token)

    def _run(self, user_message: str, *, node: Node, isolated: bool=False) -> str:
        if not isinstance(user_message, str):
            raise TypeError('用户消息必须是字符串')
        if node.agent is not self:
            raise RuntimeError('Agent 必须绑定到当前节点')
        tool_names = {tool['function']['name'] for tool in self.tool_definitions}
        missing = tool_names - node.tools.keys()
        if missing:
            raise ValueError(f'工具定义未在节点注册：{sorted(missing)}')
        messages = [{'role': 'system', 'content': self.system_prompt}] if isolated else deepcopy(self.messages)
        messages.append({'role': 'user', 'content': user_message})
        for request_number in range(1, self.max_rounds + 1):
            self.check_budget()
            while not self.inbox.empty():messages.append({'role':'user','content':self.inbox.get()})
            completion = task_completion.get()
            request_messages = deepcopy(messages)
            request_messages.extend(dict(role='user',content=t) for t in self.request_tail)
            request_messages.append({'role': 'system', 'content': f'当前请求次数：{request_number}/{self.max_rounds}。这是本次任务的模型请求上限。' + ('请在额度内使用提供的工具完成任务。' if completion else '')})
            request = {'model': self.model, 'messages': request_messages, 'max_tokens': self.max_tokens}
            if self.tool_definitions:
                request.update(tools=deepcopy(self.tool_definitions), tool_choice='auto')
            if self.extra_body is not None:
                request['extra_body'] = deepcopy(self.extra_body)
            if hasattr(self.client,'set_timeout'):self.client.set_timeout(max(.01,self.deadline-time.monotonic()))
            self.steps = request_number
            response = self.client.chat.completions.create(**request)
            self.check_budget()
            if not response.choices:
                raise RuntimeError('模型返回了空 choices')
            choice = response.choices[0]
            if choice.finish_reason == 'length':
                raise RuntimeError('模型输出被 token 上限截断')
            message = choice.message
            if not message.tool_calls:
                if not message.content or not message.content.strip():
                    raise RuntimeError('模型没有返回正文或工具调用')
                messages.append(message.model_dump(exclude_none=True))
                if completion is not None and completion() is None:
                    messages.append({'role': 'user', 'content': '任务要求尚未完成，请使用提供的工具完成。'})
                    continue
                if not isolated:
                    self.messages = messages
                return message.content
            messages.append(message.model_dump(exclude_none=True))
            for tool_call in message.tool_calls:
                self.check_budget()
                try:
                    name = tool_call.function.name
                    if name not in tool_names:
                        raise ValueError(f'工具未向模型开放：{name}')
                    arguments = json.loads(tool_call.function.arguments)
                    if not isinstance(arguments, dict):
                        raise TypeError('工具参数必须是字典')
                    from datanet.core.access_budget import current_access
                    frame = current_access.get()
                    token = current_access.set({**frame, 'visited': {node.node_id}}) if frame else None
                    try:
                        result = node.invoke_tool(name, **arguments)
                    finally:
                        if token is not None:
                            current_access.reset(token)
                    if is_dataclass(result) and (not isinstance(result, type)):
                        result = asdict(result)
                    content = json.dumps(result, ensure_ascii=False, allow_nan=False)
                except (ValueError, KeyError, TypeError) as error:
                    content = json.dumps({'error': str(error)}, ensure_ascii=False)
                messages.append({'role': 'tool', 'tool_call_id': tool_call.id, 'content': content})
            if not isolated:self.messages=deepcopy(messages)
            if completion is not None and completion() is not None:
                if not isolated:
                    self.messages = messages
                return completion()
        raise RuntimeError(f'模型请求达到 {self.max_rounds} 轮，尚未得到最终回复')

    def check_budget(self):
        if self.cancel_event.is_set():raise InterruptedError('Execution canceled')
        if time.monotonic()>=self.deadline:raise TimeoutError('Execution time budget exhausted')
    def send(self,message):
        if not isinstance(message,str):raise TypeError('Message must be text')
        self.inbox.put(message)
