"""成员、候选、表决和 Git 配置规则。"""

import hashlib
import json
import re
import time
from copy import deepcopy
from domain.json_values import thaw
from domain.core.channel_filters import normalize_channels

def _channels(module, field, default):
    return normalize_channels(module.config.get(field, default))


COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")


BRANCH_RE = re.compile(r"^(?!-)(?!.*\.\.)(?!.*//)(?!.*@\{)[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$")


REF_PREFIX_RE = re.compile(r"^refs/[A-Za-z0-9._/-]+/$")


CANDIDATE_RE = re.compile(r"^cand-[0-9a-f]{16}$")


DEFAULT_TERMINAL_REF = "pwsh"


DEFAULT_TERMINAL_CHANNELS = ["workspace"]


DEFAULT_MEMBER_CHANNEL = ["collaboration"]


DEFAULT_MEMBER_BRANCH_PREFIX = "member/"


MAX_BRANCH_LENGTH = 200


MAX_HISTORY = 50


ILLEGAL_REF_CHARS_RE = re.compile(r"[^A-Za-z0-9._/-]")


BRANCH_PREFIX_RE = re.compile(
    r"^(?!-)(?!.*\.\.)(?!.*//)(?!.*@\{)[A-Za-z0-9][A-Za-z0-9._/-]*$"
)


class _BusyError(Exception):
    """同一实例已有外部 Git 操作在进行。"""


class _GitError(Exception):
    """可记录的 Git／整合失败；detail 会进入 state.last_failure。"""

    def __init__(self, message, *, stage="git", member=None, commit=None,
                 conflict_lines=None, detail=None):
        super().__init__(message)
        self.stage = stage
        self.member = member
        self.commit = commit
        self.conflict_lines = conflict_lines or []
        self.detail = detail


def _plain(value):
    """配置和参数是冻结 JSON；读取时取可变副本。"""
    return deepcopy(thaw(value))


def _state(module):
    state = module.state
    defaults = {
        "members": {},
        "submissions": {},
        "candidate": None,
        "history": [],
        "last_failure": None,
        "busy": None,
        "sequence": 0,
        "accepted_head": None,
    }
    for key, value in defaults.items():
        if key not in state:
            state[key] = value
    return state


def _config(module):
    config = module.config
    repo = config.get("repository")
    if not isinstance(repo, str) or not repo.strip():
        raise _GitError("未配置仓库路径 repository", stage="config")
    base = config.get("base_branch", "main")
    integration = config.get("integration_branch", "nexarbor/integration")
    prefix = config.get("candidate_ref_prefix", "refs/nexarbor/candidates/")
    for label, value in (("base_branch", base), ("integration_branch", integration)):
        if not isinstance(value, str) or not BRANCH_RE.match(value):
            raise _GitError(f"配置 {label} 不是合法分支名", stage="config")
    if not isinstance(prefix, str) or not REF_PREFIX_RE.match(prefix):
        raise _GitError("配置 candidate_ref_prefix 必须是 refs/.../ 形式的引用前缀", stage="config")
    terminal_ref = config.get("terminal_ref", DEFAULT_TERMINAL_REF)
    if not isinstance(terminal_ref, str) or not terminal_ref.strip():
        raise _GitError("配置 terminal_ref 必须是工具名称", stage="config")
    channels = _plain(config.get("terminal_channels", DEFAULT_TERMINAL_CHANNELS))
    if not isinstance(channels, list) or not channels or not all(
            isinstance(item, str) and item for item in channels):
        raise _GitError("配置 terminal_channels 必须是非空频道名数组", stage="config")
    timeout = config.get("command_timeout_ms", 60000)
    if type(timeout) is not int or timeout < 1000:
        raise _GitError("配置 command_timeout_ms 必须是至少 1000 的整数", stage="config")
    lease = config.get("busy_lease_seconds", 900)
    if type(lease) is not int or lease < 30:
        raise _GitError("配置 busy_lease_seconds 必须是至少 30 的整数", stage="config")
    member_channel = _channels(module, 
        "member_channel", list(DEFAULT_MEMBER_CHANNEL)
    )
    if not member_channel and module.config.get("channel_modes", {}).get("member_channel", "allow") == "allow":
        raise _GitError(
            "成员发现频道为空；请检查 member_channel 与节点 access 授权",
            stage="config",
        )
    branch_prefix = config.get("member_branch_prefix", DEFAULT_MEMBER_BRANCH_PREFIX)
    if not isinstance(branch_prefix, str) or not BRANCH_PREFIX_RE.match(branch_prefix):
        raise _GitError(
            "配置 member_branch_prefix 必须是合法分支前缀（只含字母、数字、._/-，"
            "且不能出现 ..、// 或 @{）",
            stage="config",
        )
    return {
        "repository": repo,
        "base_branch": base,
        "integration_branch": integration,
        "candidate_ref_prefix": prefix,
        "member_channel": list(member_channel),
        "member_branch_prefix": branch_prefix,
        "terminal_ref": terminal_ref,
        "terminal_channels": channels,
        "command_timeout_ms": timeout,
        "busy_lease_seconds": lease,
    }


def _sanitize_ref_component(text):
    """把单个引用片段里的 Git 非法字符替换为 '-'，并去掉破坏引用的首尾。"""
    value = ILLEGAL_REF_CHARS_RE.sub("-", str(text))
    value = re.sub(r"\.{2,}", ".", value)
    value = re.sub(r"-{2,}", "-", value)
    value = value.strip(".-")
    while value.lower().endswith(".lock"):
        value = value[:-5].strip(".-")
    return value


def _sanitize_node_id(node_id):
    """把节点 ID 变成可拼接的合法分支片段；全被替换时回退到稳定哈希。"""
    parts = [
        part
        for part in (
            _sanitize_ref_component(piece) for piece in str(node_id).split("/")
        )
        if part
    ]
    if not parts:
        parts = ["member-" + hashlib.sha256(
            str(node_id).encode("utf-8")
        ).hexdigest()[:12]]
    return "/".join(parts)


def _member_branch(prefix, node_id):
    """成员分支 = 配置前缀 + 安全化后的节点 ID，并保证整体得到合法分支名。"""
    segment = _sanitize_node_id(node_id)
    branch = prefix + segment
    if len(branch) > MAX_BRANCH_LENGTH:
        digest = hashlib.sha256(str(node_id).encode("utf-8")).hexdigest()[:12]
        keep = max(MAX_BRANCH_LENGTH - len(prefix) - len(digest) - 1, 1)
        segment = segment[:keep].rstrip(".-") + "-" + digest
        branch = prefix + segment
    branch = "/".join(
        part
        for part in (
            _sanitize_ref_component(piece) for piece in branch.split("/")
        )
        if part
    )
    if not BRANCH_RE.match(branch):
        branch = "member/" + hashlib.sha256(
            str(node_id).encode("utf-8")
        ).hexdigest()[:12]
    return branch


def _active_members(members):
    return sorted(member_id for member_id, info in members.items() if info["active"])


def _member(members, member_id, *, require_active=True):
    info = members.get(member_id)
    if info is None:
        raise _GitError(
            f"成员“{member_id}”不在当前发现的成员集合中", stage="validate"
        )
    if require_active and not info["active"]:
        raise _GitError(f"成员“{member_id}”已退出，不能继续参与", stage="validate")
    return info


def _submission_branch(members, member_id, parameters):
    branch = parameters.get("branch")
    if branch is not None:
        if not isinstance(branch, str) or not BRANCH_RE.match(branch):
            raise _GitError("提交参数 branch 不是合法分支名", stage="validate")
        return branch
    branch = members[member_id].get("branch")
    if not branch:
        raise _GitError(f"成员“{member_id}”没有配置分支，提交时必须提供 branch", stage="validate")
    return branch


def _busy_acquire(module, operation):
    state = _state(module)
    cfg = _config(module)
    now = time.time()
    busy = state.get("busy")
    if busy and now - float(busy.get("started", 0)) < cfg["busy_lease_seconds"]:
        raise _BusyError(
            f"实例正在执行“{busy.get('operation')}”，请等待完成后再试"
        )
    token = f"{operation}:{module._access_origin.info.node_id}:{time.time_ns()}"
    state["busy"] = {
        "operation": operation,
        "started": now,
        "token": token,
    }
    return token


def _busy_release(module, token):
    state = _state(module)
    busy = state.get("busy")
    if busy and busy.get("token") == token:
        state["busy"] = None


def _record_failure(module, operation, error):
    state = _state(module)
    state["last_failure"] = {
        "at": time.time(),
        "operation": operation,
        "stage": getattr(error, "stage", "internal"),
        "message": str(error),
        "member": getattr(error, "member", None),
        "commit": getattr(error, "commit", None),
        "conflict_lines": list(getattr(error, "conflict_lines", []) or []),
        "detail": getattr(error, "detail", None),
    }


def _candidate_ref(cfg, candidate_id):
    return cfg["candidate_ref_prefix"] + candidate_id


def _candidate_id(cfg, base, submissions):
    payload = {
        "version": 1,
        "base": base,
        "integration_branch": cfg["integration_branch"],
        "submissions": [
            {"member": item["member"], "commit": item["commit"]}
            for item in sorted(submissions, key=lambda value: value["member"])
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return "cand-" + hashlib.sha256(raw).hexdigest()[:16]


def _submission_snapshot(module, members):
    submissions = _state(module)["submissions"]
    result = []
    for member_id in _active_members(members):
        item = submissions.get(member_id)
        if item is not None:
            result.append({
                "member": member_id,
                "commit": item["commit"],
                "branch": item["branch"],
            })
    return result


def _candidate_view(module, candidate):
    if candidate is None:
        return None
    state = _state(module)
    active = {
        member_id for member_id, entry in state["members"].items()
        if entry.get("active")
    }
    if candidate.get("status") == "passed":
        acceptance = candidate.get("acceptance") or candidate
        required = sorted(acceptance.get(
            "required_members", candidate.get("members", [])))
        votes = acceptance.get("votes", {})
    else:
        required = sorted(
            member_id for member_id in candidate.get("members", [])
            if member_id in active
        )
        votes = candidate.get("votes", {})
    approved = [member_id for member_id in required
                if votes.get(member_id, {}).get("decision") == "approve"]
    vetoed = [member_id for member_id in required
              if votes.get(member_id, {}).get("decision") == "veto"]
    view = deepcopy(candidate)
    view["votes"] = deepcopy(votes)
    view["required_members"] = required
    view["approved_by"] = approved
    view["vetoed_by_members"] = vetoed
    view["missing_approvals"] = [
        member_id for member_id in required if member_id not in approved
    ]
    return view


def _freeze_acceptance(candidate):
    """发布事实不随之后的成员退出或拓扑变化重算。"""
    if not isinstance(candidate.get("acceptance"), dict):
        candidate["acceptance"] = {
            "round": candidate.get("round", 1),
            "required_members": list(candidate.get(
                "required_members", candidate.get("members", []))),
            "votes": deepcopy(candidate.get("votes", {})),
            "at": candidate.get("promoted_at"),
        }


def _archive_candidate(module, candidate, reason):
    if candidate is None:
        return
    if candidate.get("status") == "passed":
        _freeze_acceptance(candidate)
    state = _state(module)
    state["history"].append({
        "id": candidate.get("id"),
        "status": candidate.get("status"),
        "round": candidate.get("round"),
        "base": candidate.get("base"),
        "commit": candidate.get("commit"),
        "members": list(candidate.get("members", [])),
        "submissions": deepcopy(candidate.get("submissions", [])),
        "acceptance": deepcopy(candidate.get("acceptance")),
        "reason": reason,
        "archived_at": time.time(),
    })
    state["history"] = state["history"][-MAX_HISTORY:]


def _require_candidate(module, parameters):
    state = _state(module)
    candidate = state.get("candidate")
    if candidate is None:
        raise _GitError("当前没有候选，请先完成提交并调用 integrate", stage="accept")
    wanted = parameters.get("candidate_id")
    if wanted is not None and wanted != candidate.get("id"):
        raise _GitError(
            f"候选“{wanted}”不是当前候选；当前候选为 {candidate.get('id')}",
            stage="accept",
        )
    return candidate


def _read(module, parameters):
    state = _state(module)
    include_history = bool(parameters.get("include_history", False))
    members = []
    for member_id in sorted(state["members"]):
        entry = state["members"][member_id]
        submission = state["submissions"].get(member_id)
        members.append({
            "id": member_id,
            "branch": entry.get("branch"),
            "active": bool(entry.get("active")),
            "left_at": entry.get("left_at"),
            "submitted_commit": submission.get("commit") if submission else None,
        })
    data = {
        "members": members,
        "submissions": [
            deepcopy(state["submissions"][member_id])
            for member_id in sorted(state["submissions"])
        ],
        "candidate": _candidate_view(module, state.get("candidate")),
        "last_failure": deepcopy(state.get("last_failure")),
        "history": deepcopy(state["history"]) if include_history else [],
        "busy": bool(state.get("busy")),
    }
    return data
