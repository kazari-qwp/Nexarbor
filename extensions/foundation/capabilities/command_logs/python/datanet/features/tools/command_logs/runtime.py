"""Persist native terminal results outside source worktrees; never rerun commands."""
from pathlib import Path
from hashlib import sha256
from uuid import uuid4
import json
from time import time
from datanet.core.application import Component
from datanet.core.record_values import redact, now
from datanet.core.state_store import JsonStore

class Plugin(Component):
    def install(self):
        key = sha256(str(self.r.directory).encode()).hexdigest()[:16]
        self.base = Path(self.r.config.get('workspace') or self.r.directory) / '.datanet' / 'command-logs' / key
        self.store = JsonStore(self.r.directory / 'command-logs/index.json', dict(logs=[]))
        self.on('tool/result', self.record)

    def directory(self, actor):
        path = self.base / sha256(actor.encode()).hexdigest()[:16]
        path.mkdir(parents=True, exist_ok=True)
        return path

    def record(self, e):
        if e['name'] not in ('pwsh', 'bash', 'exec_command', 'write_stdin', 'job_output'):
            return
        id = str(uuid4())
        result = redact(e['result'])
        content = result.get('content', [])
        text = '\n'.join(c.get('text', '') for c in content if c.get('type') == 'text')
        record = dict(id=id, actor=e['actor'], tool=e['name'], at=now(), timestamp=time(), arguments=redact(e.get('arguments', {})), result=result)
        streams = {}
        value = result.get('value') or {}
        for name in ('stdout', 'stderr'):
            stream = value.get(name) if isinstance(value, dict) else None
            if not isinstance(stream, dict):
                continue
            full = stream.get('text', '')
            complete = not stream.get('truncated', False)
            if stream.get('spillPath'):
                try:
                    full = Path(stream['spillPath']).read_text(encoding='utf-8', errors='replace')
                    complete = True
                except OSError as error:
                    stream = {**stream, 'read_error': str(error)}
            streams[name] = dict(text=redact(full), complete=complete, source=stream)
        if streams:
            record['streams'] = streams
            text = '\n'.join(name + ':\n' + stream['text'] for name, stream in streams.items())
        path = self.directory(e['actor']) / (id + '.json')
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        path.with_suffix('.txt').write_text(text or json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        self.store.mutate(lambda db: db['logs'].append(dict(id=id, actor=e['actor'], tool=e['name'], at=record['at'], timestamp=record['timestamp'], path=str(path), command=record['arguments'].get('command', '')[:160])))

    def logs(self, actor, ids=None, since=0):
        records = [i for i in self.store.data['logs'] if i['actor'] == actor and i.get('timestamp', 0) >= since]
        if ids is not None:
            selected = set(ids)
            records = [i for i in records if i['id'] in selected]
            if len(records) != len(selected):
                raise ValueError('日志不存在或不属于当前成员')
        return records

    def tool_datanet_command_logs(self, actor, p):
        if p['action'] == 'list':
            records = list(reversed(self.logs(actor)))
            offset, limit = p.get('offset', 0), p.get('limit', 20)
            return dict(logs=records[offset:offset+limit], total=len(records), next_offset=offset+limit if offset+limit < len(records) else None)
        item = self.logs(actor, [p['log_id']])[0]
        text = Path(item['path']).read_text(encoding='utf-8')
        offset, limit = p.get('offset', 0), p.get('limit', 12000)
        return dict(log_id=item['id'], content=text[offset:offset+limit], total_chars=len(text), next_offset=offset+limit if offset+limit < len(text) else None)
