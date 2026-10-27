"""Git 成果整合：发现成员，串联合并候选，全员验收后推进正式引用。"""

from copy import deepcopy

from app.transactions.locks import require_transaction_node
from domain.core import Module, access
from . import operations
from .state import _BusyError, _GitError, _config, _state, _read, _busy_acquire, _busy_release, _record_failure


class Members:
    def __init__(self, module, config):
        self._access_origin = module._access_origin
        self.channels = config["member_channel"]
        self.channel_mode = module.config.get("channel_modes", {}).get("member_channel", "allow")
        self.strength = module.strength

    @access()
    async def collect(self, node):
        if node.node_type == "agent":
            return node.info.node_id


class GitIntegratorModule(Module):
    def __init__(self, config=None, state=None, **access_settings):
        super().__init__("git.integrator.rev_2863bbe53e.rev_c376775a7e", **access_settings)
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})

    async def discover_members(self, config):
        try:
            members = [node_id for node_id in (await Members(self, config).collect()).values() if node_id is not None]
        except Exception as error:
            raise _GitError("无法沿成员发现频道查找成员：%s" % (str(error) or "请求失败"), stage="config") from error
        if not members:
            raise _GitError("没有发现可参与的 Agent 成员；请检查 member_channel、节点类型和连接", stage="config")
        return members

    async def _call(self, operation, parameters):
        return next(iter((await self._operate(operation, parameters)).values()))

    @access(channels=())
    async def _operate(self, node, operation, parameters):
        require_transaction_node(node.info.node_id)
        _state(self)
        if operation == "read":
            config = _config(self)
            await operations._sync_members(self, config)
            data = _read(self, parameters)
            data["workspace"] = {key:config[key] for key in ("repository", "base_branch", "integration_branch")}
            return data
        token = None
        try:
            config = _config(self)
            members = await operations._sync_members(self, config)
            token = _busy_acquire(self, operation)
            if operation == "integrate":
                return await operations._integrate(self, config, members)
            if operation == "promote":
                return await operations._promote_op(self, config, parameters)
            return await getattr(operations, "_" + operation)(self, config, members, parameters)
        except _BusyError:
            raise
        except Exception as error:
            if token is not None:
                _record_failure(self, operation, error)
            raise
        finally:
            if token is not None:
                _busy_release(self, token)

    async def read(self, include_history=False):
        return await self._call("read", {"include_history":include_history})

    async def submit(self, member, commit, branch=None):
        return await self._call("submit", {"member":member, "commit":commit, "branch":branch})

    async def integrate(self):
        return await self._call("integrate", {})

    async def approve(self, member, candidate_id=None, reason=None):
        return await self._call("approve", {"member":member, "candidate_id":candidate_id, "reason":reason})

    async def veto(self, member, candidate_id=None, reason=None):
        return await self._call("veto", {"member":member, "candidate_id":candidate_id, "reason":reason})

    async def leave(self, member, reason=None):
        return await self._call("leave", {"member":member, "reason":reason})

    async def reopen(self, candidate_id=None, reason=None):
        return await self._call("reopen", {"candidate_id":candidate_id, "reason":reason})

    async def promote(self, candidate_id=None):
        return await self._call("promote", {"candidate_id":candidate_id})
