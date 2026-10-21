"""An Agent's stable identity and privately owned Markdown memory."""
from pathlib import Path
from threading import RLock
import os
import tempfile
from datanet.core.node import Node


class AgentNode(Node):
    signal_type = 'agent'
    def __init__(self, node_id, name, data_kind=None, file_path=None, *, description='', creation_options=None, aggregation='sum'):
        super().__init__(node_id, name, 'agent', description=description, aggregation=aggregation)
        self.file_path = Path(file_path).resolve()
        self._memory_lock = RLock()
        from datanet.core.agent_inputs import AgentInputs
        self.inputs = AgentInputs()
        self.creation_options = dict(creation_options or {})
        self.register_agent_tool('memory_read', self.read_memory,
            description='读取自己的记忆文件。',
            parameters={'type':'object','properties':{},'additionalProperties':False})
        self.register_agent_tool('memory_write', self.write_memory,
            description='更新自己的记忆文件。',
            parameters={'type':'object','properties':{'content':{'type':'string'},'mode':{'type':'string','enum':['replace','append']}},'required':['content'],'additionalProperties':False})

    def update_inputs(self, source, **patch):
        return self.inputs.update(source, patch)

    def read_memory(self):
        with self._memory_lock:
            return {'node_id': self.node_id, 'content': self.file_path.read_text(encoding='utf-8') if self.file_path.exists() else ''}

    def write_memory(self, content, mode='replace'):
        if not isinstance(content, str) or mode not in ('replace', 'append'):
            raise ValueError('Memory requires text and replace/append mode')
        with self._memory_lock:
            if mode == 'append':
                content = self.read_memory()['content'] + content
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=self.file_path.parent, prefix='.memory-')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.file_path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        return {'node_id': self.node_id, 'written': True}
