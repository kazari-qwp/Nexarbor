"""原 Harness 执行器，使用新 Agent 节点、access 和 Tools。"""

import asyncio
from dataclasses import asdict, is_dataclass
from inspect import isawaitable
from contextlib import nullcontext

from app.runtime.context_packets import apply_context_packet
from domain.core import Tools, access


class NativeExecutor:
    def __init__(self, network, transport, *, bindings=None, states=None, locks=None):
        self.network = network
        self.transport = transport
        self.locks = locks
        self.bindings = {} if bindings is None else bindings
        self.states = {} if states is None else states
        self._available = {}
        self._tools = {}

    def binding(self, actor):
        node = self.network.get(actor)
        return node, self.bindings[actor]

    def attach(self, actor, runtime):
        agent, _ = self.binding(actor)

        def run(message, tools):
            return runtime.run(self.run(actor, message, tools=tools))["output"]

        agent.runner = run

    def _scope(self, actor, *, asynchronous):
        if self.locks is None:
            return nullcontext()
        return self.locks.access([actor]) if asynchronous else self.locks.access_sync([actor])

    async def run(self, actor, message="", *, tools=None, **options):
        async with self._scope(actor, asynchronous=True):
            return await self._run_owned(actor, message, tools=tools, **options)

    async def _run_owned(self, actor, message="", *, tools=None, **options):
        agent, binding = self.binding(actor)
        self._available[actor] = Tools(agent.available_tools().values()) if tools is None else tools
        state = self.states.setdefault(actor, {})
        request = dict(
            actor=actor, name=agent.info.name, message=message,
            timeout_seconds=max(86400, options.get("timeout_seconds", binding.get("timeout_seconds", 86400))),
            max_steps=max(100000, binding.get("max_steps", 100000)),
            session_id=state.get("session_id"), context_cursor=state.get("context_cursor"),
            model=binding.get("model"), model_signature=state.get("model_signature"),
        )
        try:
            async with self.locks.suspend_access() if self.locks is not None else nullcontext():
                with self.locks.export_owner(actor) if self.locks is not None else nullcontext() as ticket:
                    if ticket is not None:
                        request["node_access_ticket"] = ticket
                    result = await asyncio.to_thread(self.transport.host, "agent-run", request)
            if self.network.get(actor) is not agent:
                raise RuntimeError("Agent node was replaced during execution")
            if result.get("status") != "completed":
                raise RuntimeError(result.get("error") or "Agent did not complete")
            state.update(session_id=result["session_id"], executor="harness")
            return result
        except asyncio.CancelledError:
            await asyncio.to_thread(self.transport.host, "agent-cancel", dict(actor=actor))
            raise

    def _check_session(self, parameters):
        expected = parameters.get("executor_session_id")
        if expected is not None and self.states.get(parameters["actor"], {}).get("session_id") != expected:
            raise PermissionError("Executor session was replaced; discard this stale callback")

    def definitions(self, actor):
        agent, _ = self.binding(actor)
        if actor not in self._available:
            self._available[actor] = Tools(agent.available_tools().values())
        definitions, tools = [], {}
        history = self.states.setdefault(actor, {}).setdefault("tool_history", {})
        for tool in self._available[actor]:
            definition = dict(name=tool.name, description=tool.description, parameters=tool.parameters)
            definitions.append(definition)
            tools[tool.name] = tool
            history[tool.name] = dict(definition=definition)
        self._tools[actor] = tools
        return definitions

    async def prepare(self, parameters):
        async with self._scope(parameters["actor"], asynchronous=True):
            return await self._prepare_owned(parameters)

    async def _prepare_owned(self, parameters):
        self._check_session(parameters)
        actor = parameters["actor"]
        agent, binding = self.binding(actor)
        state = self.states.setdefault(actor, {})
        for reference in binding.get("prepare", []):
            target = reference.get("node", actor)
            result = await self._prepare_operation(agent, binding, reference)
            source = "prepare:" + target + ":" + reference["module"] + ":" + reference["operation"]
            apply_context_packet(agent, state, source, result)
        active = {"prepare:" + reference.get("node", actor) + ":" + reference["module"] + ":" + reference["operation"]
                  for reference in binding.get("prepare", [])}
        for source in agent.inputs.snapshot():
            if source.startswith("prepare:") and source not in active:
                agent.update_inputs(source, system_prompt="", context=[], tail=[])
        definitions = await asyncio.to_thread(self.definitions, actor)
        sources = agent.inputs.snapshot()
        history = state["tool_history"]
        current = {definition["name"] for definition in definitions}
        return dict(
            actor=actor, system_prompt="\n\n".join(value["system_prompt"] for _, value in sorted(sources.items())),
            skills=binding.get("skills", []),
            context=[dict(id=source + "/" + doc["id"], text=doc["text"])
                     for source, value in sorted(sources.items()) for doc in value["context"]],
            inputs=[dict(source=source, **event) for source, event in agent.inputs.pending()],
            tail=agent.inputs.tail(), tools=definitions,
            retained_tools=[value["definition"] for value in history.values()],
            unavailable={name: "这个工具已不在当前工具表中。" for name in history if name not in current},
        )

    async def _prepare_operation(self, origin, binding, reference):
        target = reference.get("node", origin.info.node_id)
        channels = reference.get("channels", binding.get("channels", ()))
        mode = "allow" if "channels" in reference else binding.get("channel_mode", binding.get("channel_modes", {}).get("channels", "allow"))

        @access(channels=channels, strength=binding.get("strength", 0), channel_mode=mode)
        async def call(owner, node):
            if node.info.node_id != target:
                return None
            module = node.modules.get(reference["module"])
            result = getattr(module, reference["operation"])(**reference.get("arguments", {}))
            return await result if isawaitable(result) else result

        class Preparation:
            _access_origin = origin

        return (await call(Preparation()))[target]

    async def invoke(self, parameters):
        async with self._scope(parameters["actor"], asynchronous=True):
            return await self._invoke_owned(parameters)

    async def _invoke_owned(self, parameters):
        self._check_session(parameters)
        actor, name = parameters["actor"], parameters["name"]
        tool = self._tools[actor].get(name)
        if tool is None:
            return dict(status="forbidden", errors=["这个工具已不在当前工具表中。"])
        result = tool.invoke(**parameters.get("arguments", {}))
        if isawaitable(result):
            result = await result
        return asdict(result) if is_dataclass(result) else result

    def ack(self, parameters):
        with self._scope(parameters["actor"], asynchronous=False):
            return self._ack_owned(parameters)

    def _ack_owned(self, parameters):
        self._check_session(parameters)
        agent, _ = self.binding(parameters["actor"])
        for event in parameters.get("events", []):
            agent.inputs.acknowledge(event["source"], event["id"])
        return {"ok": True}

    def bind(self, parameters):
        with self._scope(parameters["actor"], asynchronous=False):
            return self._bind_owned(parameters)

    def _bind_owned(self, parameters):
        self.binding(parameters["actor"])
        state = self.states.setdefault(parameters["actor"], {})
        state.update(session_id=parameters["session_id"], executor="harness", model_signature=parameters.get("model_signature"))
        if parameters.get("context_cursor") is not None:
            state["context_cursor"] = parameters["context_cursor"]
        return {"ok": True}

    def prune(self, parameters):
        with self._scope(parameters["actor"], asynchronous=False):
            return self._prune_owned(parameters)

    def _prune_owned(self, parameters):
        self._check_session(parameters)
        actor = parameters["actor"]
        retained = set(parameters.get("referenced", [])) | {definition["name"] for definition in self.definitions(actor)}
        history = self.states[actor]["tool_history"]
        for name in list(history):
            if name not in retained:
                history.pop(name)
        return list(history)

    async def capture(self, bindings):
        return await asyncio.to_thread(self.transport.host, "agent-context-capture", dict(bindings=bindings))

    async def restore(self, cursors):
        return await asyncio.to_thread(self.transport.host, "agent-context-restore", dict(contexts=cursors, transactional=True))
