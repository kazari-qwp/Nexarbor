"""编排运行、任务交接与错误历史。"""

import asyncio
import copy
import time
from domain.json_values import thaw
from domain.core.channel_filters import resolve

def _configured_channels(module, field, defaults):
    channels = module.config.get(field, defaults)
    mode = module.config.get("channel_modes", {}).get(field, "allow")
    universe = module._access_origin._channel_names() if mode == "deny" else ()
    return list(resolve(channels, mode, universe))


ACTIVE_STATUSES = ("discussing", "executing", "reviewing")


MAX_RUNS = 20


MAX_ERRORS = 20


MAX_TASKS = 20


DEFAULT_REVIEW_CHANNELS = ["collaboration.review"]


DEFAULT_SUBMIT_CHANNELS = ["collaboration"]


DEFAULT_ACCEPT_CHANNELS = ["collaboration"]


DEFAULT_REOPEN_REASON = "成员否决后重开验收"


DEFAULT_DISCUSSION_MODULE = "discussion.session.rev_697d80a33d"


DEFAULT_BOARD_MODULE = "collab.board.rev_9191e2380f.rev_96569f0263"


DEFAULT_INTEGRATOR_MODULE = "git.integrator.rev_2863bbe53e.rev_c376775a7e"


class _Fail(Exception):
    """当前操作无法继续；在锁外转成中文错误结果。"""


_INSTANCE_LOCKS = {}


def _instance_lock(module):
    """同一模块实例的写操作串行化；状态仍只保存在实例里。"""
    loop = asyncio.get_running_loop()
    key = (id(module), id(loop))
    lock = _INSTANCE_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _INSTANCE_LOCKS[key] = lock
    return lock


def _plain(value):
    return copy.deepcopy(thaw(value))


def _state(module):
    state = module.state
    if "run" not in state:
        state["run"] = None
    if "runs" not in state:
        state["runs"] = []
    if "errors" not in state:
        state["errors"] = []
    return state


def _error(state, operation, message):
    entry = {
        "at": time.time(),
        "operation": operation,
        "message": str(message),
    }
    errors = list(state.get("errors") or [])
    errors.append(entry)
    state["errors"] = errors[-MAX_ERRORS:]


def _archive_run(state):
    """把当前运行写入历史；同一 id 只保留一份，最多 20 条。"""
    run = state.get("run")
    if not run:
        return
    snapshot = _plain(run)
    runs = [item for item in (state.get("runs") or [])
            if isinstance(item, dict) and item.get("id") != snapshot.get("id")]
    runs.append(snapshot)
    state["runs"] = runs[-MAX_RUNS:]


def _config_module(module, field, default):
    """下游模块编号：配置非空时用配置值，否则沿用旧装配的默认值。"""
    value = module.config.get(field)
    if isinstance(value, str) and value.strip():
        return value
    return default


def _discussion_module(module):
    return _config_module(module, "discussion_module", DEFAULT_DISCUSSION_MODULE)


def _board_module(module):
    return _config_module(module, "board_module", DEFAULT_BOARD_MODULE)


def _integrator_module(module):
    return _config_module(module, "integrator_module", DEFAULT_INTEGRATOR_MODULE)


def _review_channels(module):
    return _configured_channels(module, "review_channel", DEFAULT_REVIEW_CHANNELS)


def _accept_channels(module):
    return _configured_channels(module, "accept_channel", DEFAULT_ACCEPT_CHANNELS)


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _task_paths(value):
    if not isinstance(value, (list, tuple)):
        return []
    return [str(path) for path in value if isinstance(path, str) and path.strip()]


def _normalize_task(item, artifact, run, index):
    """把讨论成果中的任务映射成协作板接受的 {title, paths, detail}。"""
    plain = _plain(item) if isinstance(item, dict) else {}
    title = _text(plain.get("title"))
    if not title:
        title = _text(artifact.get("title")) or _text(run.get("task")) or f"任务 {index}"
    # 同时存在 detail 与 description 时优先 detail；只有 description 时转成 detail。
    detail = _text(plain.get("detail")) or _text(plain.get("description"))
    if not detail:
        detail = title
    return {
        "title": title[:120],
        "paths": _task_paths(plain.get("paths")),
        "detail": detail[:2000],
    }


def _raw_tasks(value):
    return list(value) if isinstance(value, (list, tuple)) else []


def _normalize_tasks(artifact, decision, run):
    """按下游真实接口选择任务来源。

    discussion.session 0.1.0 的 status.artifact 只有 run/title/at，
    任务列表实际落在 status.decision.tasks，因此顺序为：
    1) artifact.tasks 非空数组；2) decision.tasks；3) 用成果标题生成一个回退任务。
    """
    raw_tasks = _raw_tasks(artifact.get("tasks"))
    if not raw_tasks:
        raw_tasks = _raw_tasks(decision.get("tasks"))
    tasks = []
    for index, item in enumerate(raw_tasks[:MAX_TASKS], start=1):
        if isinstance(item, dict):
            tasks.append(_normalize_task(item, artifact, run, index))
    if not tasks:
        title = _text(artifact.get("title")) or _text(run.get("task")) or "讨论成果"
        summary = _text(artifact.get("summary")) or _text(artifact.get("body"))
        tasks = [{
            "title": title[:120],
            "paths": [],
            "detail": (summary or title)[:2000],
        }]
    return tasks


def _integrate_reason(params):
    """integrate 的可选 reason：缺省返回 None，非法值直接报错。"""
    reason = params.get("reason")
    if reason is None:
        return None
    if not isinstance(reason, str):
        raise _Fail("整合参数 reason 必须是字符串")
    if len(reason) > 500:
        raise _Fail("整合参数 reason 不能超过 500 个字符")
    return reason


def _candidate_label(candidate, run):
    candidate_id = candidate.get("id") if isinstance(candidate, dict) else None
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        candidate_id = run.get("candidate")
    if isinstance(candidate_id, str) and candidate_id.strip():
        return candidate_id
    return "当前候选"


def _promotion_failed(candidate, run):
    raise _Fail(
        f"候选 {_candidate_label(candidate, run)} 已获全员认可，但推进整合分支失败"
        "（promotion_failed），不能再次整合，请改用 promote 重试"
    )
