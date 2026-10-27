"""通过本节点的真实终端工具执行原 Git 算法。"""

import re
import time
from .state import (
    BRANCH_RE,
    COMMIT_RE,
    _GitError,
    _active_members,
    _candidate_id,
    _candidate_ref,
    _freeze_acceptance,
    _state,
    _submission_snapshot,
)

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


async def _terminal(module, command, cfg):
    """调用真实宿主终端端口，并按 harness-tool-result/v1 读取结果。"""
    arguments = {
        "description": "执行 Git 成果整合命令",
        "command": command,
        "workdir": cfg["repository"],
        "timeoutMs": cfg["command_timeout_ms"],
    }
    try:
        tool = next((tool for tool in module._access_origin.tools
                     if tool.name == cfg["terminal_ref"]), None)
        if tool is None:
            raise PermissionError("本节点没有该宿主终端工具")
        envelope = await tool.invoke(**arguments)
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


async def _git(module, args, cfg, *, check=True):
    command = "git " + " ".join(_ps_quote(item) for item in args)
    value = await _terminal(module, command, cfg)
    stdout = ((value.get("stdout") or {}).get("text") or "").strip()
    stderr = ((value.get("stderr") or {}).get("text") or "").strip()
    code = value.get("exitCode")
    if check and code != 0:
        message = stderr or stdout or f"Git 命令退出码 {code}"
        raise _GitError(f"Git 命令失败：{message}", stage="git",
                        detail={"args": args, "exitCode": code, "stderr": stderr})
    return code, stdout, stderr


async def _rev_parse(module, cfg, spec):
    code, stdout, _ = await _git(module, ["rev-parse", "--verify", spec], cfg, check=False)
    if code != 0 or not stdout:
        return None
    return stdout.splitlines()[-1].strip()


async def _is_ancestor(module, cfg, commit, ref):
    code, _, stderr = await _git(
        module, ["merge-base", "--is-ancestor", commit, ref], cfg, check=False
    )
    if code == 0:
        return True
    if code == 1:
        return False
    raise _GitError(f"无法判断提交祖先关系：{stderr or commit}", stage="git")


async def _integration_base(module, cfg):
    branch_ref = "refs/heads/" + cfg["integration_branch"]
    head = await _rev_parse(module, cfg, branch_ref + "^{commit}")
    if head is not None:
        return head
    base = await _rev_parse(module, cfg, "refs/heads/" + cfg["base_branch"] + "^{commit}")
    if base is None:
        raise _GitError(
            f"整合分支“{cfg['integration_branch']}”和基线分支“{cfg['base_branch']}”都不存在",
            stage="git",
        )
    return base


async def _validate_commit(module, cfg, member_id, commit, branch):
    if not isinstance(commit, str) or not COMMIT_RE.match(commit):
        raise _GitError(f"成员“{member_id}”的提交必须是 7-64 位十六进制哈希", stage="validate",
                        member=member_id, commit=commit)
    if not isinstance(branch, str) or not BRANCH_RE.match(branch):
        raise _GitError(f"成员“{member_id}”的分支名不合法", stage="validate",
                        member=member_id, commit=commit)
    full = await _rev_parse(module, cfg, commit + "^{commit}")
    if full is None:
        raise _GitError(f"提交 {commit} 不存在或不是提交对象", stage="validate",
                        member=member_id, commit=commit)
    branch_ref = "refs/heads/" + branch
    branch_head = await _rev_parse(module, cfg, branch_ref + "^{commit}")
    if branch_head is None:
        raise _GitError(f"成员“{member_id}”的分支“{branch}”不存在", stage="validate",
                        member=member_id, commit=commit)
    if not await _is_ancestor(module, cfg, full, branch_ref):
        raise _GitError(
            f"提交 {full} 不在成员“{member_id}”的分支“{branch}”上",
            stage="validate", member=member_id, commit=full,
        )
    return full


async def _merge_tree(module, cfg, head, commit, member_id):
    code, stdout, stderr = await _git(
        module, ["merge-tree", "--write-tree", head, commit], cfg, check=False
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


async def _commit_tree(module, cfg, tree, head, commit, candidate_id, submissions):
    args = [
        "-c", "user.name=Nexarbor",
        "-c", "user.email=nexarbor@localhost",
        "commit-tree", tree,
        "-p", head,
        "-p", commit,
        "-m", _commit_message(candidate_id, cfg, submissions),
    ]
    code, stdout, stderr = await _git(module, args, cfg, check=False)
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


async def _build_candidate(module, cfg, members):
    base = await _integration_base(module, cfg)
    submissions = _submission_snapshot(module, members)
    active = _active_members(members)
    if not active:
        raise _GitError("没有仍在参与的成员，无法形成候选", stage="validate")
    missing = [member_id for member_id in active
               if member_id not in _state(module)["submissions"]]
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
            module, cfg, item["member"], item["commit"], item["branch"]
        )
        item["commit"] = full
        if await _is_ancestor(module, cfg, full, base):
            raise _GitError(
                f"成员“{item['member']}”的提交 {full} 已在整合基线中，请提交新的成果",
                stage="validate", member=item["member"], commit=full,
            )

    candidate_id = _candidate_id(cfg, base, ordered)
    head = base
    for item in ordered:
        tree = await _merge_tree(module, cfg, head, item["commit"], item["member"])
        head = await _commit_tree(
            module, cfg, tree, head, item["commit"], candidate_id, ordered
        )

    candidate_ref = _candidate_ref(cfg, candidate_id)
    code, stdout, stderr = await _git(
        module, ["update-ref", candidate_ref, head], cfg, check=False
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


async def _promote(module, cfg, candidate):
    branch_ref = "refs/heads/" + cfg["integration_branch"]
    current = await _rev_parse(module, cfg, branch_ref + "^{commit}")
    target = candidate["commit"]
    base = candidate["base"]
    if current == target:
        candidate["status"] = "passed"
        candidate["promoted_at"] = candidate.get("promoted_at") or time.time()
        _freeze_acceptance(candidate)
        _state(module)["accepted_head"] = target
        return
    if current is not None and current != base:
        raise _GitError(
            "整合分支在候选创建后被更新，拒绝覆盖外部成果；候选未通过",
            stage="promote",
            detail={"expected": base, "actual": current},
        )
    old = current if current is not None else "0" * len(base)
    code, stdout, stderr = await _git(
        module, ["update-ref", branch_ref, target, old], cfg, check=False
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
    _state(module)["accepted_head"] = target
