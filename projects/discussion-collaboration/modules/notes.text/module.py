"""通用文本便笺：在 text_file 节点正文上追加、读取、覆盖和清空，读写均经 ctx。"""
import json
from datetime import datetime, timezone

from datanet.core.module_protocol import ComponentResult

MAX_SEEN = 200
DEFAULT_SEPARATOR = "\n\n"


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _version(ctx):
    value = ctx.state.get("version", 0)
    return value if isinstance(value, int) and value >= 0 else 0


def _seen(ctx):
    entries = []
    for entry in ctx.state.get("seen", []) or []:
        entries.append({"key": entry["key"], "fingerprint": entry["fingerprint"]})
    return entries


def _fingerprint(operation, text):
    return json.dumps(
        {"operation": operation, "text": text},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )


def _check_duplicate(seen, key, fingerprint):
    """同键同内容视为重复请求；同键不同内容一律拒绝。"""
    if key is None:
        return False
    for entry in seen:
        if entry["key"] != key:
            continue
        if entry["fingerprint"] != fingerprint:
            raise ValueError("幂等键“%s”已用于不同内容，不能复用" % key)
        return True
    return False


def _read_content(ctx):
    result = ctx.read({"method": "key", "key": "content"})
    if result.get("status") != "ok":
        errors = result.get("errors") or []
        raise RuntimeError("读取便笺正文失败：" + ("；".join(str(e) for e in errors) or "未知错误"))
    items = result.get("items") or []
    if not items:
        return ""
    value = items[0].get("content", "")
    if not isinstance(value, str):
        raise RuntimeError("便笺正文不是文本")
    return value


def _write_content(ctx, text):
    result = ctx.write("content", text)
    if result.get("status") != "ok":
        errors = result.get("errors") or []
        raise RuntimeError("写入便笺正文失败：" + ("；".join(str(e) for e in errors) or "未知错误"))


def _ok_view(ctx, content):
    return {
        "title": ctx.config.get("title", "便笺"),
        "content": content,
        "version": _version(ctx),
        "updated_at": ctx.state.get("updated_at", ""),
    }


async def _append(ctx, parameters):
    text = parameters["text"]
    key = parameters.get("key")
    fingerprint = _fingerprint("append", text)
    separator = ctx.config.get("separator", DEFAULT_SEPARATOR)
    if not isinstance(separator, str):
        separator = DEFAULT_SEPARATOR
    limit = int(ctx.config.get("max_chars", 20000))
    # 读取正文、判断重复、写入正文与推进版本必须在同一短事务内完成，避免并发丢写。
    async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
        seen = _seen(ctx)
        version = _version(ctx)
        content = _read_content(ctx)
        if _check_duplicate(seen, key, fingerprint):
            return {
                "version": version,
                "length": len(content),
                "appended": 0,
                "duplicate": True,
            }
        addition = (separator if content else "") + text
        if len(content) + len(addition) > limit:
            raise ValueError(
                "追加后正文将超过配置上限 %d 个字符（当前 %d，追加 %d），本次未写入"
                % (limit, len(content), len(addition))
            )
        new_content = content + addition
        _write_content(ctx, new_content)
        if key is not None:
            seen.append({"key": key, "fingerprint": fingerprint})
        ctx.state["seen"] = seen[-MAX_SEEN:]
        ctx.state["version"] = version + 1
        ctx.state["updated_at"] = _utc_now()
        return {
            "version": version + 1,
            "length": len(new_content),
            "appended": len(addition),
            "duplicate": False,
        }


async def _replace(ctx, parameters):
    text = parameters["text"]
    key = parameters.get("key")
    fingerprint = _fingerprint("replace", text)
    limit = int(ctx.config.get("max_chars", 20000))
    async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
        seen = _seen(ctx)
        version = _version(ctx)
        if _check_duplicate(seen, key, fingerprint):
            content = _read_content(ctx)
            return {"version": version, "length": len(content), "duplicate": True}
        if len(text) > limit:
            raise ValueError(
                "替换正文超过配置上限 %d 个字符（给定 %d），本次未写入" % (limit, len(text))
            )
        _write_content(ctx, text)
        if key is not None:
            seen.append({"key": key, "fingerprint": fingerprint})
        ctx.state["seen"] = seen[-MAX_SEEN:]
        ctx.state["version"] = version + 1
        ctx.state["updated_at"] = _utc_now()
        return {"version": version + 1, "length": len(text), "duplicate": False}


async def _clear(ctx):
    async with ctx.network.lock_nodes([ctx.node_id], timeout=20):
        version = _version(ctx)
        content = _read_content(ctx)
        _write_content(ctx, "")
        ctx.state["version"] = version + 1
        ctx.state["updated_at"] = _utc_now()
        return {"version": version + 1, "cleared": len(content)}


async def execute(ctx, activation):
    if activation.kind != "access":
        return ComponentResult(status="error", error="文本便笺只接受访问请求")
    try:
        operation = activation.operation
        if operation == "append":
            return ComponentResult(data=await _append(ctx, activation.parameters))
        if operation == "replace":
            return ComponentResult(data=await _replace(ctx, activation.parameters))
        if operation == "read":
            return ComponentResult(data=_ok_view(ctx, _read_content(ctx)))
        if operation == "clear":
            return ComponentResult(data=await _clear(ctx))
        raise ValueError("不支持的文本便笺操作")
    except Exception as error:
        return ComponentResult(status="error", error=str(error))
