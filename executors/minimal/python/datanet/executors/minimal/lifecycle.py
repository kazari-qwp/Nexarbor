"""Lifecycle helpers for the optional in-process Agent implementation."""
from threading import get_ident

def restart_agent(node, *, wait: bool=True) -> None:
    """等待现有任务结束，先构建新实例，成功后替换；失败保留旧实例。"""
    previous = node.agent
    if previous is None:
        raise RuntimeError('该节点尚未配置 Agent')
    if previous._running_thread == get_ident():
        raise RuntimeError('Agent 不能在自身任务执行中同步重启')
    if not previous._lifecycle_lock.acquire(blocking=wait):
        raise RuntimeError('目标 Agent 正忙，请稍后重试')
    try:
        if node.agent is not previous:
            raise RuntimeError('Agent 实例已改变，请重新发起重启')
        replacement = previous.rebuild()
        node.agent = replacement
    finally:
        previous._lifecycle_lock.release()

def update_agent_prompt(node, content: str, *, restart: bool=True) -> dict:
    """Persist to the bound prompt path; validate before retaining the edit."""
    import os
    import tempfile
    from pathlib import Path
    if not isinstance(content, str) or not content.strip():
        raise ValueError('提示词必须是非空字符串')
    if type(restart) is not bool:
        raise TypeError('restart必须是bool')
    previous = node.agent
    if previous is None:
        raise RuntimeError('该节点尚未配置 Agent')
    if previous._running_thread == get_ident() or not previous._lifecycle_lock.acquire(blocking=False):
        raise RuntimeError('目标 Agent 正忙，请稍后重试')
    try:
        if node.agent is not previous:
            raise RuntimeError('Agent实例已改变，请重试')
        path = previous.prompt_path
        original = path.read_bytes()

        def replace(destination, data):
            fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix='.prompt-')
            try:
                with os.fdopen(fd, 'wb') as file:
                    file.write(data)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, destination)
            finally:
                Path(temporary).unlink(missing_ok=True)
        replace(path, content.encode('utf-8'))
        try:
            replacement = previous.rebuild()
            replace(path.with_name(path.name + '.bak'), original)
        except Exception:
            replace(path, original)
            raise
        if restart:
            node.agent = replacement
        return {'prompt_path': str(path), 'restarted': restart}
    finally:
        previous._lifecycle_lock.release()
