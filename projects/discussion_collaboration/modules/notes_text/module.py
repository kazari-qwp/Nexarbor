"""Markdown 文本便笺；保留原版本、分隔符、长度上限和幂等规则。"""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from domain.core import CallableTool, Module, access

TOOLS=json.loads(Path(__file__).with_name('tools.json').read_text(encoding='utf-8'))

MAX_SEEN = 200
DEFAULT_SEPARATOR = "\n\n"


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _version(module):
    value = module.state.get("version", 0)
    return value if isinstance(value, int) and value >= 0 else 0


def _seen(module):
    entries = []
    for entry in module.state.get("seen", []) or []:
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


def _ok_view(module, content):
    return {
        "title": module.config.get("title", "便笺"),
        "content": content,
        "version": _version(module),
        "updated_at": module.state.get("updated_at", ""),
    }


async def _append(module, node, parameters):
    text = parameters["text"]
    key = parameters.get("key")
    fingerprint = _fingerprint("append", text)
    separator = module.config.get("separator", DEFAULT_SEPARATOR)
    if not isinstance(separator, str):
        separator = DEFAULT_SEPARATOR
    limit = int(module.config.get("max_chars", 20000))
    # 读取正文、判断重复、写入正文与推进版本必须在同一短事务内完成，避免并发丢写。
    async with module.transaction([node.info.node_id], timeout=20):
        seen = _seen(module)
        version = _version(module)
        content = node.dataer.read()
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
        node.dataer.write(new_content)
        if key is not None:
            seen.append({"key": key, "fingerprint": fingerprint})
        module.state["seen"] = seen[-MAX_SEEN:]
        module.state["version"] = version + 1
        module.state["updated_at"] = _utc_now()
        return {
            "version": version + 1,
            "length": len(new_content),
            "appended": len(addition),
            "duplicate": False,
        }


async def _replace(module, node, parameters):
    text = parameters["text"]
    key = parameters.get("key")
    fingerprint = _fingerprint("replace", text)
    limit = int(module.config.get("max_chars", 20000))
    async with module.transaction([node.info.node_id], timeout=20):
        seen = _seen(module)
        version = _version(module)
        if _check_duplicate(seen, key, fingerprint):
            content = node.dataer.read()
            return {"version": version, "length": len(content), "duplicate": True}
        if len(text) > limit:
            raise ValueError(
                "替换正文超过配置上限 %d 个字符（给定 %d），本次未写入" % (limit, len(text))
            )
        node.dataer.write(text)
        if key is not None:
            seen.append({"key": key, "fingerprint": fingerprint})
        module.state["seen"] = seen[-MAX_SEEN:]
        module.state["version"] = version + 1
        module.state["updated_at"] = _utc_now()
        return {"version": version + 1, "length": len(text), "duplicate": False}


async def _clear(module, node):
    async with module.transaction([node.info.node_id], timeout=20):
        version = _version(module)
        content = node.dataer.read()
        node.dataer.write("")
        module.state["version"] = version + 1
        module.state["updated_at"] = _utc_now()
        return {"version": version + 1, "cleared": len(content)}



class NotesTextModule(Module):
    def __init__(self, transaction, config=None, state=None, **access_settings):
        super().__init__('notes.text', **access_settings)
        self.transaction = transaction
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        for spec in TOOLS:self.tools._add(CallableTool(spec['id'],getattr(self,spec['operation']),spec['description'],deepcopy(spec['parameters'])))

    def _bind(self, node):
        super()._bind(node)
        source_id=sha256((node.info.node_id+'\0'+self.module_id).encode()).hexdigest()[:24]
        for tool,spec in zip(self.tools,TOOLS):
            tool.name='mod_'+sha256((source_id+'\0'+spec['id']).encode()).hexdigest()[:24]
            tool.description=node.info.node_id+' · '+spec['name']+' · '+spec['description']

    async def read(self):return next(iter((await self._read()).values()))
    async def append(self, text, key=None):return next(iter((await self._append_local(dict(text=text,key=key))).values()))
    async def replace(self, text, key=None):return next(iter((await self._replace_local(dict(text=text,key=key))).values()))
    async def clear(self):return next(iter((await self._clear_local()).values()))

    @access(channels=())
    async def _read(self, node):return _ok_view(self,node.dataer.read())

    @access(channels=())
    async def _append_local(self, node, parameters):return await _append(self,node,parameters)

    @access(channels=())
    async def _replace_local(self, node, parameters):return await _replace(self,node,parameters)

    @access(channels=())
    async def _clear_local(self, node):return await _clear(self,node)
