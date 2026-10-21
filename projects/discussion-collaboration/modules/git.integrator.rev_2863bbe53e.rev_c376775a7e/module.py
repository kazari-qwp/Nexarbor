"""Git 成果整合与全员验收。

职责边界：
* 沿成员发现频道动态发现真实 Agent 节点，节点 ID 即成员 ID；
* 接收各成员在独立 worktree／分支上产生的提交；
* 校验提交确实存在且可达该成员分支；
* 以成员 ID 排序后串行合并到候选引用，冲突只中止候选，不删除个人提交；
* 候选通过全员认可后才把整合分支推进到候选提交；
* 否决、退出、重复请求、失败和重开都有显式状态。

不负责认领任务、创建团队或调用模型。所有 Git 操作都通过节点公开的
宿主终端端口执行，模块自身只读写 ctx.config / ctx.state。
"""

import hashlib
import json
import re
import time
from copy import deepcopy

from datanet.core.json_values import thaw
from datanet.core.module_protocol import ComponentResult

COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
BRANCH_RE = re.compile(r"^(?!-)(?!.*\.\.)(?!.*//)(?!.*@\{)[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$")
REF_PREFIX_RE = re.compile(r"^refs/[A-Za-z0-9._/-]+/$")
CANDIDATE_RE = re.compile(r"^cand-[0-9a-f]{16}$")

DEFAULT_TERMINAL_REF = "harness:pwsh"
DEFAULT_TERMINAL_CHANNELS = ["workspace"]
DEFAULT_MEMBER_CHANNEL = ["collaboration"]
DEFAULT_MEMBER_BRANCH_PREFIX = "member/"
MAX_BRANCH_LENGTH = 200
MAX_HISTORY = 50

# Git 引用（含分支名）非法字符；"~" 在预设重复单元展开后常见的节点 ID 中出现。
ILLEGAL_REF_CHARS_RE = re.compile(r"[^A-Za-z0-9._/-]")
# 配置中的分支前缀必须是可直接拼接的合法引用片段。
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


def _state(ctx):
    state = ctx.state
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


def _config(ctx):
    config = ctx.config
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
    if not isinstance(terminal_ref, str) or ":" not in terminal_ref:
        raise _GitError("配置 terminal_ref 必须是“提供者:工具”形式的端口引用", stage="config")
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
    member_channel = ctx.filter_channels(
        "member_channel", list(DEFAULT_MEMBER_CHANNEL)
    )
    if not member_channel:
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


async def _discover_members(ctx, channels):
    """沿成员发现频道查找真实 Agent 节点，返回去重的节点 ID。"""
    try:
        nodes = await ctx.network.nodes(channels=list(channels))
    except Exception as error:
        raise _GitError(
            "无法沿成员发现频道查找成员：%s" % (str(error) or "请求失败"),
            stage="config",
        ) from error
    discovered = []
    seen = set()
    for node in nodes or []:
        metadata = node.metadata
        if not isinstance(metadata, dict):
            continue
        if metadata.get("node_type") != "agent":
            continue
        node_id = metadata.get("node_id")
        if not isinstance(node_id, str) or not node_id or node_id in seen:
            continue
        seen.add(node_id)
        discovered.append(node_id)
    if not discovered:
        raise _GitError(
            "没有发现可参与的 Agent 成员；请检查 member_channel、节点类型和连接",
            stage="config",
        )
    return discovered


async def _sync_members(ctx, cfg):
    """按拓扑重新发现成员；显式退出不会被重新发现悄悄恢复。"""
    raw = _plain(ctx.config.get("members", []))
    if not isinstance(raw, list):
        raise _GitError("配置 members 必须是成员数组", stage="config")
    overrides = {}
    for item in raw:
        if not isinstance(item, dict):
            raise _GitError("配置 members 的每一项必须是 {id, branch} 对象", stage="config")
        member_id = item.get("id")
        if not isinstance(member_id, str) or not member_id.strip():
            raise _GitError("成员 id 必须是非空字符串", stage="config")
        if member_id in overrides:
            raise _GitError(f"成员 id“{member_id}”重复", stage="config")
        branch = item.get("branch")
        if branch is not None and (not isinstance(branch, str) or not BRANCH_RE.match(branch)):
            raise _GitError(f"成员“{member_id}”的 branch 不是合法分支名", stage="config")
        overrides[member_id] = branch

    discovered = await _discover_members(ctx, cfg["member_channel"])
    state = _state(ctx)
    members = state["members"]
    discovered_set = set(discovered)
    for member_id in discovered:
        branch = overrides.get(member_id) or _member_branch(
            cfg["member_branch_prefix"], member_id
        )
        entry = members.get(member_id)
        if entry is None:
            entry = {
                "active": True,
                "branch": branch,
                "left_at": None,
                "removed_by_config": False,
            }
            members[member_id] = entry
        else:
            entry["branch"] = branch
            if entry.get("removed_by_config"):
                # 只是暂时没被发现（例如频道或拓扑短暂变化）的成员可以恢复；
                # 通过 leave 显式退出的成员保持退出。
                entry["active"] = True
                entry["removed_by_config"] = False
                entry["left_at"] = None
    for member_id, entry in members.items():
        if member_id in discovered_set:
            continue
        if entry.get("active"):
            entry["active"] = False
            entry["removed_by_config"] = True
            entry["left_at"] = time.time()
    return {
        member_id: {
            "branch": members[member_id]["branch"],
            "active": bool(members[member_id].get("active")),
        }
        for member_id in discovered
    }


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


def _busy_acquire(ctx, operation):
    state = _state(ctx)
    cfg = _config(ctx)
    now = time.time()
    busy = state.get("busy")
    if busy and now - float(busy.get("started", 0)) < cfg["busy_lease_seconds"]:
        raise _BusyError(
            f"实例正在执行“{busy.get('operation')}”，请等待完成后再试"
        )
    token = f"{operation}:{ctx.node_id}:{time.time_ns()}"
    state["busy"] = {
        "operation": operation,
        "started": now,
        "token": token,
    }
    return token


def _busy_release(ctx, token):
    state = _state(ctx)
    busy = state.get("busy")
    if busy and busy.get("token") == token:
        state["busy"] = None


def _record_failure(ctx, operation, error):
    state = _state(ctx)
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


def _ps_quote(value):
    """PowerShell 双引号参数；模块不会把仓库路径拼入命令。"""
    text = str(value)
    return '"' + text.replace("`", "``").replace('"', '`"') + '"'


def _envelope_text(envelope):
    content = envelope.get("content")
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        if parts:
            return "\n".join(parts)
    return ""


async def _terminal(ctx, command, cfg):
    """调用真实宿主终端端口，并按 harness-tool-result/v1 读取结果。"""
    arguments = {
        "description": "执行 Git 成果整合命令",
        "command": command,
        "workdir": cfg["repository"],
        "timeoutMs": cfg["command_timeout_ms"],
    }
    try:
        envelope = await ctx.network.invoke(
            ctx.node_id,
            cfg["terminal_ref"],
            arguments,
            channels=list(cfg["terminal_channels"]),
        )
    except PermissionError as error:
        raise _GitError(
            f"没有调用宿主终端 {cfg['terminal_ref']} 的权限：{error}",
            stage="workspace",
        ) from error
    except Exception as error:
        raise _GitError(f"调用宿主终端失败：{error}", stage="workspace") from error

    if not isinstance(envelope, dict):
        raise _GitError("宿主终端返回了无法识别的结果", stage="workspace")
    if envelope.get("isError"):
        message = _envelope_text(envelope) or "宿主终端报告失败"
        raise _GitError(message, stage="workspace")
    value = envelope.get("value")
    if not isinstance(value, dict):
        raise _GitError("宿主终端结果缺少 value", stage="workspace")
    kind = value.get("kind")
    if kind != "foreground":
        job = value.get("jobId")
        raise _GitError(
            f"宿主终端未在前台完成（kind={kind}，job={job}）",
            stage="workspace",
            detail={"kind": kind, "jobId": job},
        )
    if value.get("timedOut") or value.get("aborted"):
        raise _GitError("宿主终端命令超时或被中止", stage="workspace")
    if value.get("exitCode") is None:
        raise _GitError("宿主终端没有返回退出码", stage="workspace")
    return value


async def _git(ctx, args, cfg, *, check=True):
    command = "git " + " ".join(_ps_quote(item) for item in args)
    value = await _terminal(ctx, command, cfg)
    stdout = ((value.get("stdout") or {}).get("text") or "").strip()
    stderr = ((value.get("stderr") or {}).get("text") or "").strip()
    code = value.get("exitCode")
    if check and code != 0:
        message = stderr or stdout or f"Git 命令退出码 {code}"
        raise _GitError(f"Git 命令失败：{message}", stage="git",
                        detail={"args": args, "exitCode": code, "stderr": stderr})
    return code, stdout, stderr


async def _rev_parse(ctx, cfg, spec):
    code, stdout, _ = await _git(ctx, ["rev-parse", "--verify", spec], cfg, check=False)
    if code != 0 or not stdout:
        return None
    return stdout.splitlines()[-1].strip()


async def _is_ancestor(ctx, cfg, commit, ref):
    code, _, stderr = await _git(
        ctx, ["merge-base", "--is-ancestor", commit, ref], cfg, check=False
    )
    if code == 0:
        return True
    if code == 1:
        return False
    raise _GitError(f"无法判断提交祖先关系：{stderr or commit}", stage="git")


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


def _submission_snapshot(ctx, members):
    submissions = _state(ctx)["submissions"]
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


async def _integration_base(ctx, cfg):
    branch_ref = "refs/heads/" + cfg["integration_branch"]
    head = await _rev_parse(ctx, cfg, branch_ref + "^{commit}")
    if head is not None:
        return head
    base = await _rev_parse(ctx, cfg, "refs/heads/" + cfg["base_branch"] + "^{commit}")
    if base is None:
        raise _GitError(
            f"整合分支“{cfg['integration_branch']}”和基线分支“{cfg['base_branch']}”都不存在",
            stage="git",
        )
    return base


async def _validate_commit(ctx, cfg, member_id, commit, branch):
    if not isinstance(commit, str) or not COMMIT_RE.match(commit):
        raise _GitError(f"成员“{member_id}”的提交必须是 7-64 位十六进制哈希", stage="validate",
                        member=member_id, commit=commit)
    if not isinstance(branch, str) or not BRANCH_RE.match(branch):
        raise _GitError(f"成员“{member_id}”的分支名不合法", stage="validate",
                        member=member_id, commit=commit)
    full = await _rev_parse(ctx, cfg, commit + "^{commit}")
    if full is None:
        raise _GitError(f"提交 {commit} 不存在或不是提交对象", stage="validate",
                        member=member_id, commit=commit)
    branch_ref = "refs/heads/" + branch
    branch_head = await _rev_parse(ctx, cfg, branch_ref + "^{commit}")
    if branch_head is None:
        raise _GitError(f"成员“{member_id}”的分支“{branch}”不存在", stage="validate",
                        member=member_id, commit=commit)
    if not await _is_ancestor(ctx, cfg, full, branch_ref):
        raise _GitError(
            f"提交 {full} 不在成员“{member_id}”的分支“{branch}”上",
            stage="validate", member=member_id, commit=full,
        )
    return full


async def _merge_tree(ctx, cfg, head, commit, member_id):
    code, stdout, stderr = await _git(
        ctx, ["merge-tree", "--write-tree", head, commit], cfg, check=False
    )
    lines = [line for line in (stdout + "\n" + stderr).splitlines() if line.strip()]
    if code == 1:
        conflicts = [
            line for line in lines
            if "CONFLICT" in line.upper() or "冲突" in line
        ]
        raise _GitError(
            f"成员“{member_id}”的提交与已整合成果冲突；个人提交仍保留，请解决后重新提交",
            stage="merge", member=member_id, commit=commit,
            conflict_lines=conflicts or lines[-8:],
            detail={"head": head},
        )
    if code != 0:
        raise _GitError(
            f"合并成员“{member_id}”的提交失败：{stderr or stdout or code}",
            stage="merge", member=member_id, commit=commit,
            detail={"head": head, "exitCode": code},
        )
    tree = lines[0].strip() if lines else ""
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", tree):
        raise _GitError(
            f"合并成员“{member_id}”的提交后没有得到有效树对象",
            stage="merge", member=member_id, commit=commit,
            detail={"output": lines[:8]},
        )
    return tree


def _commit_message(candidate_id, cfg, submissions):
    lines = [
        f"Nexarbor-Candidate: {candidate_id}",
        f"Nexarbor-Integration: {cfg['integration_branch']}",
    ]
    for item in submissions:
        lines.append(f"Nexarbor-Submission: {item['member']} {item['commit']}")
    return "\n".join(lines)


async def _commit_tree(ctx, cfg, tree, head, commit, candidate_id, submissions):
    args = [
        "-c", "user.name=Nexarbor",
        "-c", "user.email=nexarbor@localhost",
        "commit-tree", tree,
        "-p", head,
        "-p", commit,
        "-m", _commit_message(candidate_id, cfg, submissions),
    ]
    code, stdout, stderr = await _git(ctx, args, cfg, check=False)
    if code != 0:
        raise _GitError(
            f"创建候选提交失败：{stderr or stdout or code}", stage="merge",
            detail={"exitCode": code},
        )
    oid = stdout.splitlines()[-1].strip() if stdout else ""
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", oid):
        raise _GitError("创建候选提交后没有得到有效提交哈希", stage="merge",
                        detail={"output": stdout[:200]})
    return oid


async def _build_candidate(ctx, cfg, members):
    base = await _integration_base(ctx, cfg)
    submissions = _submission_snapshot(ctx, members)
    active = _active_members(members)
    if not active:
        raise _GitError("没有仍在参与的成员，无法形成候选", stage="validate")
    missing = [member_id for member_id in active
               if member_id not in _state(ctx)["submissions"]]
    if missing:
        raise _GitError("以下成员尚未提交成果：" + "、".join(missing), stage="validate")

    ordered = sorted(submissions, key=lambda item: item["member"])
    seen = {}
    for item in ordered:
        previous = seen.get(item["commit"])
        if previous is not None:
            raise _GitError(
                f"提交 {item['commit']} 同时由成员“{previous}”和“{item['member']}”提交，"
                "不能重复计入候选",
                stage="validate", member=item["member"], commit=item["commit"],
            )
        seen[item["commit"]] = item["member"]

    for item in ordered:
        full = await _validate_commit(
            ctx, cfg, item["member"], item["commit"], item["branch"]
        )
        item["commit"] = full
        if await _is_ancestor(ctx, cfg, full, base):
            raise _GitError(
                f"成员“{item['member']}”的提交 {full} 已在整合基线中，请提交新的成果",
                stage="validate", member=item["member"], commit=full,
            )

    candidate_id = _candidate_id(cfg, base, ordered)
    head = base
    for item in ordered:
        tree = await _merge_tree(ctx, cfg, head, item["commit"], item["member"])
        head = await _commit_tree(
            ctx, cfg, tree, head, item["commit"], candidate_id, ordered
        )

    candidate_ref = _candidate_ref(cfg, candidate_id)
    code, stdout, stderr = await _git(
        ctx, ["update-ref", candidate_ref, head], cfg, check=False
    )
    if code != 0:
        raise _GitError(
            f"写入候选引用失败：{stderr or stdout or code}", stage="merge",
            detail={"candidate_ref": candidate_ref},
        )
    now = time.time()
    return {
        "id": candidate_id,
        "round": 1,
        "base": base,
        "commit": head,
        "ref": candidate_ref,
        "members": active,
        "submissions": ordered,
        "votes": {},
        "rounds": [],
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "vetoed_by": None,
        "stale_reason": None,
        "promoted_at": None,
    }


def _candidate_view(ctx, candidate):
    if candidate is None:
        return None
    state = _state(ctx)
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


def _archive_candidate(ctx, candidate, reason):
    if candidate is None:
        return
    if candidate.get("status") == "passed":
        _freeze_acceptance(candidate)
    state = _state(ctx)
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


async def _promote(ctx, cfg, candidate):
    branch_ref = "refs/heads/" + cfg["integration_branch"]
    current = await _rev_parse(ctx, cfg, branch_ref + "^{commit}")
    target = candidate["commit"]
    base = candidate["base"]
    if current == target:
        candidate["status"] = "passed"
        candidate["promoted_at"] = candidate.get("promoted_at") or time.time()
        _freeze_acceptance(candidate)
        _state(ctx)["accepted_head"] = target
        return
    if current is not None and current != base:
        raise _GitError(
            "整合分支在候选创建后被更新，拒绝覆盖外部成果；候选未通过",
            stage="promote",
            detail={"expected": base, "actual": current},
        )
    old = current if current is not None else "0" * len(base)
    code, stdout, stderr = await _git(
        ctx, ["update-ref", branch_ref, target, old], cfg, check=False
    )
    if code != 0:
        raise _GitError(
            f"推进整合分支失败：{stderr or stdout or code}",
            stage="promote",
            detail={"expected": old, "target": target},
        )
    candidate["status"] = "passed"
    candidate["promoted_at"] = time.time()
    candidate["updated_at"] = time.time()
    _freeze_acceptance(candidate)
    _state(ctx)["accepted_head"] = target


async def _evaluate(ctx, cfg, candidate):
    if candidate.get("status") != "pending":
        return
    state = _state(ctx)
    active = {
        member_id for member_id, entry in state["members"].items()
        if entry.get("active")
    }
    required = sorted(
        member_id for member_id in candidate.get("members", [])
        if member_id in active
    )
    candidate["required_members"] = required
    if not required:
        candidate["status"] = "stale"
        candidate["stale_reason"] = "没有仍在参与的成员"
        candidate["updated_at"] = time.time()
        return
    votes = candidate.get("votes", {})
    vetoed = [member_id for member_id in required
              if votes.get(member_id, {}).get("decision") == "veto"]
    if vetoed:
        candidate["status"] = "vetoed"
        candidate["vetoed_by"] = vetoed[0]
        candidate["updated_at"] = time.time()
        return
    approved = [member_id for member_id in required
                if votes.get(member_id, {}).get("decision") == "approve"]
    if len(approved) == len(required):
        try:
            await _promote(ctx, cfg, candidate)
        except _GitError:
            candidate["status"] = "promotion_failed"
            candidate["updated_at"] = time.time()
            raise


async def _submit(ctx, cfg, members, parameters):
    member_id = parameters.get("member")
    if not isinstance(member_id, str) or not member_id:
        raise _GitError("submit 需要成员 id", stage="validate")
    _member(members, member_id)
    commit = parameters.get("commit")
    branch = _submission_branch(members, member_id, parameters)
    full = await _validate_commit(ctx, cfg, member_id, commit, branch)
    base = await _integration_base(ctx, cfg)
    if await _is_ancestor(ctx, cfg, full, base):
        raise _GitError(
            f"提交 {full} 已在整合基线中，请提交新的成果",
            stage="validate", member=member_id, commit=full,
        )

    state = _state(ctx)
    submissions = state["submissions"]
    for other_id, item in submissions.items():
        if other_id != member_id and item.get("commit") == full:
            raise _GitError(
                f"提交 {full} 已由成员“{other_id}”提交，不能重复计入候选",
                stage="validate", member=member_id, commit=full,
            )
    existing = submissions.get(member_id)
    if existing is not None and existing.get("commit") == full:
        return {
            "duplicate": True,
            "member": member_id,
            "commit": full,
            "branch": existing.get("branch", branch),
            "candidate_status": (state.get("candidate") or {}).get("status"),
        }

    previous_candidate = state.get("candidate")
    if previous_candidate and previous_candidate.get("status") == "pending":
        previous_candidate["status"] = "stale"
        previous_candidate["stale_reason"] = f"成员“{member_id}”提交了新成果"
        previous_candidate["updated_at"] = time.time()

    state["sequence"] = int(state.get("sequence", 0)) + 1
    submissions[member_id] = {
        "member": member_id,
        "commit": full,
        "branch": branch,
        "sequence": state["sequence"],
        "submitted_at": time.time(),
    }
    return {
        "duplicate": False,
        "member": member_id,
        "commit": full,
        "branch": branch,
        "candidate_status": (state.get("candidate") or {}).get("status"),
    }


async def _integrate(ctx, cfg, members):
    state = _state(ctx)
    active = _active_members(members)
    if not active:
        raise _GitError("没有仍在参与的成员，无法整合", stage="validate")
    missing = [member_id for member_id in active
               if member_id not in state["submissions"]]
    if missing:
        raise _GitError("以下成员尚未提交成果：" + "、".join(missing), stage="validate")

    base = await _integration_base(ctx, cfg)
    submissions = _submission_snapshot(ctx, members)
    candidate_id = _candidate_id(cfg, base, submissions)
    current = state.get("candidate")
    if current is not None and current.get("id") == candidate_id:
        status = current.get("status")
        if status == "pending":
            return {"duplicate": True, "candidate": _candidate_view(ctx, current)}
        if status == "passed":
            return {"duplicate": True, "candidate": _candidate_view(ctx, current)}
        if status == "vetoed":
            raise _GitError(
                f"候选 {candidate_id} 已被否决，请调用 reopen 重开验收",
                stage="accept", detail={"candidate_id": candidate_id},
            )
        if status == "promotion_failed":
            raise _GitError(
                f"候选 {candidate_id} 已获全员认可，但整合分支推进失败；请调用 promote 重试",
                stage="promote", detail={"candidate_id": candidate_id},
            )

    candidate = await _build_candidate(ctx, cfg, members)
    if current is not None:
        reason = f"被新候选 {candidate['id']} 取代"
        _archive_candidate(ctx, current, reason)
    state["candidate"] = candidate
    state["last_failure"] = None
    return {"duplicate": False, "candidate": _candidate_view(ctx, candidate)}


def _require_candidate(ctx, parameters):
    state = _state(ctx)
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


async def _approve(ctx, cfg, members, parameters):
    member_id = parameters.get("member")
    if not isinstance(member_id, str) or not member_id:
        raise _GitError("approve 需要成员 id", stage="validate")
    _member(members, member_id)
    candidate = _require_candidate(ctx, parameters)
    if member_id not in candidate.get("members", []):
        raise _GitError(f"成员“{member_id}”不在候选 {candidate['id']} 的参与名单中", stage="accept")
    votes = candidate.setdefault("votes", {})
    existing = votes.get(member_id)
    status = candidate.get("status")
    if status == "passed":
        if existing and existing.get("decision") == "approve":
            return {"duplicate": True, "candidate": _candidate_view(ctx, candidate)}
        raise _GitError("候选已通过，不能再次变更；请提交新成果", stage="accept")
    if status == "vetoed":
        raise _GitError("候选已被否决，请先调用 reopen", stage="accept")
    if status != "pending":
        raise _GitError(f"候选当前状态为 {status}，不能认可", stage="accept")
    if existing and existing.get("decision") == "approve":
        return {"duplicate": True, "candidate": _candidate_view(ctx, candidate)}
    if existing and existing.get("decision") == "veto":
        raise _GitError("该成员此前已否决此候选，请先调用 reopen", stage="accept")
    votes[member_id] = {
        "decision": "approve",
        "reason": parameters.get("reason"),
        "at": time.time(),
    }
    candidate["updated_at"] = time.time()
    await _evaluate(ctx, cfg, candidate)
    return {"duplicate": False, "candidate": _candidate_view(ctx, candidate)}


async def _veto(ctx, cfg, members, parameters):
    member_id = parameters.get("member")
    if not isinstance(member_id, str) or not member_id:
        raise _GitError("veto 需要成员 id", stage="validate")
    _member(members, member_id)
    candidate = _require_candidate(ctx, parameters)
    if member_id not in candidate.get("members", []):
        raise _GitError(f"成员“{member_id}”不在候选 {candidate['id']} 的参与名单中", stage="accept")
    status = candidate.get("status")
    votes = candidate.setdefault("votes", {})
    existing = votes.get(member_id)
    reason = parameters.get("reason")
    if status == "passed":
        raise _GitError("候选已通过，不能否决；请提交新成果", stage="accept")
    if status == "vetoed":
        if existing and existing.get("decision") == "veto" and existing.get("reason") == reason:
            return {"duplicate": True, "candidate": _candidate_view(ctx, candidate)}
        raise _GitError("候选已被否决；如需重新表决请调用 reopen", stage="accept")
    if status != "pending":
        raise _GitError(f"候选当前状态为 {status}，不能否决", stage="accept")
    if existing and existing.get("decision") == "veto" and existing.get("reason") == reason:
        return {"duplicate": True, "candidate": _candidate_view(ctx, candidate)}
    votes[member_id] = {
        "decision": "veto",
        "reason": reason,
        "at": time.time(),
    }
    candidate["status"] = "vetoed"
    candidate["vetoed_by"] = member_id
    candidate["updated_at"] = time.time()
    return {"duplicate": False, "candidate": _candidate_view(ctx, candidate)}


async def _leave(ctx, cfg, members, parameters):
    member_id = parameters.get("member")
    if not isinstance(member_id, str) or not member_id:
        raise _GitError("leave 需要成员 id", stage="validate")
    info = members.get(member_id)
    if info is None:
        raise _GitError(
            f"成员“{member_id}”不在当前发现的成员集合中", stage="validate"
        )
    if not info["active"]:
        return {
            "duplicate": True,
            "member": member_id,
            "candidate": _candidate_view(ctx, _state(ctx).get("candidate")),
        }
    state = _state(ctx)
    candidate = state.get("candidate")
    if candidate is not None and candidate.get("status") == "passed":
        _freeze_acceptance(candidate)
    entry = state["members"][member_id]
    entry["active"] = False
    entry["left_at"] = time.time()
    entry["removed_by_config"] = False
    entry["leave_reason"] = parameters.get("reason")
    if (candidate is not None and candidate.get("status") != "passed"
            and member_id in candidate.get("members", [])):
        candidate.get("votes", {}).pop(member_id, None)
        if candidate.get("status") == "vetoed":
            remaining_veto = any(
                vote.get("decision") == "veto"
                for member, vote in candidate.get("votes", {}).items()
                if member in candidate.get("members", [])
                and state["members"].get(member, {}).get("active")
            )
            if not remaining_veto:
                candidate["status"] = "pending"
                candidate["vetoed_by"] = None
        if candidate.get("status") == "pending":
            await _evaluate(ctx, cfg, candidate)
    return {
        "duplicate": False,
        "member": member_id,
        "candidate": _candidate_view(ctx, state.get("candidate")),
    }


async def _reopen(ctx, cfg, members, parameters):
    candidate = _require_candidate(ctx, parameters)
    status = candidate.get("status")
    if status == "promotion_failed":
        raise _GitError("候选已获全员认可，请调用 promote 重试推进整合分支", stage="accept")
    if status != "vetoed":
        raise _GitError(f"只有被否决的候选可以重开；当前状态为 {status}", stage="accept")
    state = _state(ctx)
    active = {
        member_id for member_id, entry in state["members"].items()
        if entry.get("active")
    }
    required = [member_id for member_id in candidate.get("members", [])
                if member_id in active]
    if not required:
        raise _GitError("没有仍在参与的成员，不能重开验收", stage="accept")
    candidate.setdefault("rounds", []).append({
        "round": candidate.get("round", 1),
        "status": "vetoed",
        "vetoed_by": candidate.get("vetoed_by"),
        "votes": deepcopy(candidate.get("votes", {})),
        "reason": parameters.get("reason"),
        "closed_at": time.time(),
    })
    candidate["round"] = int(candidate.get("round", 1)) + 1
    candidate["votes"] = {}
    candidate["status"] = "pending"
    candidate["vetoed_by"] = None
    candidate["updated_at"] = time.time()
    return {"duplicate": False, "candidate": _candidate_view(ctx, candidate)}


async def _promote_op(ctx, cfg, parameters):
    candidate = _require_candidate(ctx, parameters)
    status = candidate.get("status")
    if status == "passed":
        return {"duplicate": True, "candidate": _candidate_view(ctx, candidate)}
    if status != "promotion_failed":
        raise _GitError(f"候选当前状态为 {status}，不需要推进整合分支", stage="promote")
    await _promote(ctx, cfg, candidate)
    return {"duplicate": False, "candidate": _candidate_view(ctx, candidate)}


def _read(ctx, parameters):
    state = _state(ctx)
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
        "candidate": _candidate_view(ctx, state.get("candidate")),
        "last_failure": deepcopy(state.get("last_failure")),
        "history": deepcopy(state["history"]) if include_history else [],
        "busy": bool(state.get("busy")),
    }
    return data


async def execute(ctx, activation):
    if activation.kind != "access":
        return ComponentResult(status="error", error="Git 整合模块只接受访问请求")

    operation = activation.operation
    parameters = _plain(activation.parameters)
    if operation == "read":
        try:
            cfg = _config(ctx)
            await _sync_members(ctx, cfg)
            data = _read(ctx, parameters)
            data['workspace'] = {key: cfg[key] for key in ('repository', 'base_branch', 'integration_branch')}
            return ComponentResult(data=data)
        except Exception as error:
            return ComponentResult(status="error", error=str(error))

    if operation not in {"submit", "integrate", "approve", "veto",
                         "leave", "reopen", "promote"}:
        return ComponentResult(status="error", error=f"不支持的操作：{operation}")

    token = None
    try:
        cfg = _config(ctx)
        members = await _sync_members(ctx, cfg)
        token = _busy_acquire(ctx, operation)
        if operation == "submit":
            data = await _submit(ctx, cfg, members, parameters)
        elif operation == "integrate":
            data = await _integrate(ctx, cfg, members)
        elif operation == "approve":
            data = await _approve(ctx, cfg, members, parameters)
        elif operation == "veto":
            data = await _veto(ctx, cfg, members, parameters)
        elif operation == "leave":
            data = await _leave(ctx, cfg, members, parameters)
        elif operation == "reopen":
            data = await _reopen(ctx, cfg, members, parameters)
        else:
            data = await _promote_op(ctx, cfg, parameters)
        return ComponentResult(data=data)
    except _BusyError as error:
        return ComponentResult(status="error", error=str(error))
    except Exception as error:
        if token is not None:
            _record_failure(ctx, operation, error)
        return ComponentResult(status="error", error=str(error))
    finally:
        if token is not None:
            _busy_release(ctx, token)
