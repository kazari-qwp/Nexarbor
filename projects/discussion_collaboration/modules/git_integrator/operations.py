"""Git 提交、候选构建和全员验收；busy 租约串行外部写操作。"""

import time
from copy import deepcopy
from .state import (
    BRANCH_RE,
    _GitError,
    _active_members,
    _archive_candidate,
    _candidate_id,
    _candidate_view,
    _freeze_acceptance,
    _member,
    _member_branch,
    _plain,
    _require_candidate,
    _state,
    _submission_branch,
    _submission_snapshot,
)
from .git import (
    _build_candidate,
    _integration_base,
    _is_ancestor,
    _promote,
    _validate_commit,
)

async def _sync_members(module, cfg):
    """按拓扑重新发现成员；显式退出不会被重新发现悄悄恢复。"""
    raw = _plain(module.config.get("members", []))
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

    discovered = await module.discover_members(cfg)
    state = _state(module)
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


async def _evaluate(module, cfg, candidate):
    if candidate.get("status") != "pending":
        return
    state = _state(module)
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
            await _promote(module, cfg, candidate)
        except _GitError:
            candidate["status"] = "promotion_failed"
            candidate["updated_at"] = time.time()
            raise


async def _submit(module, cfg, members, parameters):
    member_id = parameters.get("member")
    if not isinstance(member_id, str) or not member_id:
        raise _GitError("submit 需要成员 id", stage="validate")
    _member(members, member_id)
    commit = parameters.get("commit")
    branch = _submission_branch(members, member_id, parameters)
    full = await _validate_commit(module, cfg, member_id, commit, branch)
    base = await _integration_base(module, cfg)
    if await _is_ancestor(module, cfg, full, base):
        raise _GitError(
            f"提交 {full} 已在整合基线中，请提交新的成果",
            stage="validate", member=member_id, commit=full,
        )

    state = _state(module)
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


async def _integrate(module, cfg, members):
    state = _state(module)
    active = _active_members(members)
    if not active:
        raise _GitError("没有仍在参与的成员，无法整合", stage="validate")
    missing = [member_id for member_id in active
               if member_id not in state["submissions"]]
    if missing:
        raise _GitError("以下成员尚未提交成果：" + "、".join(missing), stage="validate")

    base = await _integration_base(module, cfg)
    submissions = _submission_snapshot(module, members)
    candidate_id = _candidate_id(cfg, base, submissions)
    current = state.get("candidate")
    if current is not None and current.get("id") == candidate_id:
        status = current.get("status")
        if status == "pending":
            return {"duplicate": True, "candidate": _candidate_view(module, current)}
        if status == "passed":
            return {"duplicate": True, "candidate": _candidate_view(module, current)}
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

    candidate = await _build_candidate(module, cfg, members)
    if current is not None:
        reason = f"被新候选 {candidate['id']} 取代"
        _archive_candidate(module, current, reason)
    state["candidate"] = candidate
    state["last_failure"] = None
    return {"duplicate": False, "candidate": _candidate_view(module, candidate)}


async def _approve(module, cfg, members, parameters):
    member_id = parameters.get("member")
    if not isinstance(member_id, str) or not member_id:
        raise _GitError("approve 需要成员 id", stage="validate")
    _member(members, member_id)
    candidate = _require_candidate(module, parameters)
    if member_id not in candidate.get("members", []):
        raise _GitError(f"成员“{member_id}”不在候选 {candidate['id']} 的参与名单中", stage="accept")
    votes = candidate.setdefault("votes", {})
    existing = votes.get(member_id)
    status = candidate.get("status")
    if status == "passed":
        if existing and existing.get("decision") == "approve":
            return {"duplicate": True, "candidate": _candidate_view(module, candidate)}
        raise _GitError("候选已通过，不能再次变更；请提交新成果", stage="accept")
    if status == "vetoed":
        raise _GitError("候选已被否决，请先调用 reopen", stage="accept")
    if status != "pending":
        raise _GitError(f"候选当前状态为 {status}，不能认可", stage="accept")
    if existing and existing.get("decision") == "approve":
        return {"duplicate": True, "candidate": _candidate_view(module, candidate)}
    if existing and existing.get("decision") == "veto":
        raise _GitError("该成员此前已否决此候选，请先调用 reopen", stage="accept")
    votes[member_id] = {
        "decision": "approve",
        "reason": parameters.get("reason"),
        "at": time.time(),
    }
    candidate["updated_at"] = time.time()
    await _evaluate(module, cfg, candidate)
    return {"duplicate": False, "candidate": _candidate_view(module, candidate)}


async def _veto(module, cfg, members, parameters):
    member_id = parameters.get("member")
    if not isinstance(member_id, str) or not member_id:
        raise _GitError("veto 需要成员 id", stage="validate")
    _member(members, member_id)
    candidate = _require_candidate(module, parameters)
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
            return {"duplicate": True, "candidate": _candidate_view(module, candidate)}
        raise _GitError("候选已被否决；如需重新表决请调用 reopen", stage="accept")
    if status != "pending":
        raise _GitError(f"候选当前状态为 {status}，不能否决", stage="accept")
    if existing and existing.get("decision") == "veto" and existing.get("reason") == reason:
        return {"duplicate": True, "candidate": _candidate_view(module, candidate)}
    votes[member_id] = {
        "decision": "veto",
        "reason": reason,
        "at": time.time(),
    }
    candidate["status"] = "vetoed"
    candidate["vetoed_by"] = member_id
    candidate["updated_at"] = time.time()
    return {"duplicate": False, "candidate": _candidate_view(module, candidate)}


async def _leave(module, cfg, members, parameters):
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
            "candidate": _candidate_view(module, _state(module).get("candidate")),
        }
    state = _state(module)
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
            await _evaluate(module, cfg, candidate)
    return {
        "duplicate": False,
        "member": member_id,
        "candidate": _candidate_view(module, state.get("candidate")),
    }


async def _reopen(module, cfg, members, parameters):
    candidate = _require_candidate(module, parameters)
    status = candidate.get("status")
    if status == "promotion_failed":
        raise _GitError("候选已获全员认可，请调用 promote 重试推进整合分支", stage="accept")
    if status != "vetoed":
        raise _GitError(f"只有被否决的候选可以重开；当前状态为 {status}", stage="accept")
    state = _state(module)
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
    return {"duplicate": False, "candidate": _candidate_view(module, candidate)}


async def _promote_op(module, cfg, parameters):
    candidate = _require_candidate(module, parameters)
    status = candidate.get("status")
    if status == "passed":
        return {"duplicate": True, "candidate": _candidate_view(module, candidate)}
    if status != "promotion_failed":
        raise _GitError(f"候选当前状态为 {status}，不需要推进整合分支", stage="promote")
    await _promote(module, cfg, candidate)
    return {"duplicate": False, "candidate": _candidate_view(module, candidate)}
