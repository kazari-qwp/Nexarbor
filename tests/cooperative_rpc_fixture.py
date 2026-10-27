"""Fixture host: start the actual project group as its root caller; all Agent tools use production RPC."""
import asyncio
import sys
from app.runtime.requester import as_requester
from adapt.harness.backend.transport import Transport
from projects.discussion_collaboration.runtime import DiscussionProject

sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
project = DiscussionProject(sys.argv[1])
transport = Transport(project.backend)
async def call(operation, parameters):
    with as_requester("root"):
        return await getattr(project.backend.network.get("collab").modules.get("cooperation.group"), operation)(**parameters)
async def settle():
    while project.backend.signals._active:
        await asyncio.gather(*(project.backend.signals.wait(key) for key in tuple(project.backend.signals._active)))
    return {key: value["status"] for key, value in project.backend.signals.records.items()}
transport.routes["cooperative_start"] = lambda p: transport.runtime.run(call("start", p))
transport.routes["cooperative_status"] = lambda p: transport.runtime.run(call("status", p))
transport.routes["signals_wait"] = lambda p: transport.runtime.run(settle())
transport.run(sys.stdin)
