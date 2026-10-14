"""讨论黑板：读取上轮快照、追加本轮发言、程序归档与调度。"""
from threading import Lock
from uuid import uuid4
from functools import partial
from datanet.core.agent import task_completion
from datanet.core.node import NodeResult
from datanet.core.access_budget import current_access, active_agent
from datanet.core.delegation import call_chain, request_budget, MAX_DEPTH, MAX_DELEGATIONS
from datanet.components.nodes.text_file_node import TextFileNode

class DiscussionBoardNode(TextFileNode):

    def __init__(self, node_id, name, data_kind, file_path, *, members, leader_id, recorder_id, project_id, notebook_id, output_id, description='', project_ids=None):
        super().__init__(node_id, name, data_kind, file_path, description=description)
        self.tools.pop('read', None)
        self.tool_definitions.pop('read', None)
        self.tools.pop('write', None)
        self.tool_definitions.pop('write', None)
        if not isinstance(members, list) or not members or (not all((isinstance(x, str) and x for x in members))):
            raise ValueError('members 必须为非空节点ID列表')
        if len(set(members)) != len(members) or leader_id not in members or recorder_id not in members or (leader_id == recorder_id):
            raise ValueError('成员不得重复，Leader和Recorder必须是不同成员')
        if not all((isinstance(x, str) and x for x in (project_id, notebook_id, output_id))):
            raise ValueError('文档节点ID必须非空')
        self.members = list(members)
        self.leader_id, self.recorder_id = (leader_id, recorder_id)
        self.project_id, self.notebook_id, self.output_id = (project_id, notebook_id, output_id)
        self.project_ids = list(project_ids) if project_ids is not None else [project_id]
        if not self.project_ids or not all((isinstance(x, str) and x for x in self.project_ids)) or len(set(self.project_ids)) != len(self.project_ids):
            raise ValueError('project_ids 必须为不重复的非空节点ID列表')
        self._network = None
        self.register_tool('load_project', self.load_project, description='读取本组全部项目资料，按节点分别返回正文，供框架在讨论开始时首次注入成员上下文。', parameters={'type': 'object', 'properties': {}, 'additionalProperties': False}, read_only=True)
        self._discussion_lock = Lock()
        self.current_round = 0
        self.total_rounds = 8
        self._active_member = None
        self._turn_result = None
        self.register_tool('run_discussion', self.run_discussion, description='触发固定轮数小组讨论，保留成员会话；代码归档、更新上轮快照并清空追加区；最后要求Recorder写输出黑板，返回节点ID。需要网络配置的成员委托许可。', parameters={'type': 'object', 'properties': {'task': {'type': 'string'}, 'rounds': {'type': 'integer', 'minimum': 1, 'default': 8}, 'strength': {'type': 'number', 'minimum': 0}}, 'required': ['task'], 'additionalProperties': False})

    def load_project(self):
        documents = []
        for target in self.project_ids:
            if not any((n.node_id == target for n, _ in self._network.walk(self.node_id, direction='read', strength=0))):
                return NodeResult(status='forbidden', errors=['项目资料读取连接已断开'])
            result = self._network.nodes[target].read({'method': 'key', 'key': 'content'})
            if result.status != 'ok':
                return result
            node = self._network.nodes[target]
            documents.append({'node_id': target, 'name': node.name, 'description': node.description, 'content': result.items[0]['content']})
        return NodeResult(items=documents)

    def bind_network(self, network):
        self._network = network

    def attach_member_tools(self):
        for member in self.members:
            node = self._network.nodes[member]
            node.register_agent_tool('read_round', self._read_round_for_member, description='读取上轮讨论快照。', parameters={'type': 'object', 'properties': {}, 'additionalProperties': False})
            node.register_agent_tool('submit_round', partial(self.finish_member, member), description='向公共黑板提交本轮发言并结束本轮任务。每轮只能提交或跳过一次。', parameters={'type': 'object', 'properties': {'content': {'type': 'string'}}, 'required': ['content'], 'additionalProperties': False})
            node.register_agent_tool('skip_round', partial(self.finish_member, member, skip=True), description='跳过本轮发言并结束本轮任务，可说明理由。', parameters={'type': 'object', 'properties': {'content': {'type': 'string'}}, 'additionalProperties': False})

    def _read_round_for_member(self):
        return self._read_key('content')

    def finish_member(self, member, content='', *, skip=False):
        acting = active_agent.get()
        if member != self._active_member or (acting and acting[1] != member) or self._turn_result is not None:
            return NodeResult(status='forbidden', errors=['不在当前成员轮次或已经完成'])
        if not isinstance(content, str) or (not skip and (not content.strip())):
            return NodeResult(status='error', errors=['提交发言不能为空'])
        text = ('[跳过本轮] ' if skip else '') + content
        if not any((node.node_id == self.node_id for node, _, _ in self._network.walk_states(member, direction='write', strength=2))):
            return NodeResult(status='forbidden', errors=['讨论黑板不在成员写入范围内'])
        result = self._append_submission('content', f'\n## 第{self.current_round}轮 · {member}\n{text}\n', mode='append')
        if result.status == 'ok':
            self._turn_result = text
        return result

    def get_schema(self):
        return {'kind': 'discussion_board', 'key': 'content', 'read': 'previous_round_snapshot', 'write_modes': [], 'access_tools': ['read_round', 'submit_round', 'skip_round'], 'members': self.members.copy(), 'leader_id': self.leader_id, 'recorder_id': self.recorder_id, 'project_id': self.project_id, 'project_ids': self.project_ids.copy(), 'notebook_id': self.notebook_id, 'output_id': self.output_id}

    @property
    def previous_path(self):
        return self.file_path.with_name(self.file_path.stem + '.previous.md')

    def _read_key(self, key):
        if key != 'content':
            return NodeResult(status='not_found')
        with self._lock:
            try:
                content = self.previous_path.read_text(encoding='utf-8') if self.previous_path.exists() else ''
                return NodeResult(items=[{'content': content}], sources=[{'node_id': self.node_id, 'key': 'content', 'snapshot': 'previous_round'}])
            except (OSError, UnicodeError) as error:
                return NodeResult(status='error', errors=[str(error)])

    def read(self, request):
        return NodeResult(status='forbidden', errors=['讨论黑板仅允许通过read_round读取快照'])

    def write(self, key, value, *, mode='append'):
        return NodeResult(status='forbidden', errors=['讨论黑板仅允许通过submit_round或skip_round提交'])

    def _append_submission(self, key, value, *, mode='append'):
        if mode != 'append':
            return NodeResult(status='forbidden', errors=['讨论黑板只允许append'])
        if key != 'content' or not isinstance(value, str):
            return NodeResult(status='error', errors=['key必须为content，value必须为字符串'])
        with self._lock:
            try:
                self.file_path.parent.mkdir(parents=True, exist_ok=True)
                current = self.file_path.read_text(encoding='utf-8') if self.file_path.exists() else ''
                self._atomic_bytes(self.file_path, (current + value).encode('utf-8'))
                return NodeResult(items=[{'appended': True}], sources=[{'node_id': self.node_id}])
            except (OSError, UnicodeError) as error:
                return NodeResult(status='error', errors=[str(error)])

    def _finish_round(self, archive_path):
        with self._lock:
            content = self.file_path.read_bytes() if self.file_path.exists() else b''
            self._atomic_bytes(archive_path, content)
            self._atomic_bytes(self.previous_path, content)
            self._atomic_bytes(self.file_path, b'')

    def run_discussion(self, task, rounds=8, strength=0):
        acting = active_agent.get()
        if acting is not None and acting[1] in self.members:
            return NodeResult(status='forbidden', errors=['小组成员不能自行启动讨论调度'])
        if not self._discussion_lock.acquire(blocking=False):
            return NodeResult(status='busy', errors=['讨论正在执行'])
        chain_token = budget_token = None
        completed = 0
        try:
            if not isinstance(task, str) or not task.strip() or type(rounds) is not int or (rounds < 1):
                raise ValueError('task必须非空，rounds必须为正整数')
            network = self._network
            if network is None:
                raise ValueError('黑板尚未绑定网络')
            chain = call_chain.get()
            if self.node_id in chain or len(chain) + 1 >= MAX_DEPTH:
                raise ValueError('拒绝循环或过深讨论调用')
            budget = request_budget.get()
            if budget is None:
                budget = {'calls': 0}
                budget_token = request_budget.set(budget)
            if budget['calls'] + rounds * len(self.members) + 1 > MAX_DELEGATIONS:
                raise ValueError('讨论轮数和成员数超过本次委托预算')
            states = {node.node_id: (node, remaining) for node, _, remaining in network.walk_states(self.node_id, strength=strength)}
            permissions = network.delegation_permissions.get(self.node_id, [])
            for member in self.members:
                if member not in permissions or member not in states or states[member][0].agent is None:
                    raise ValueError(f'成员未获委托许可、不可达或没有Agent：{member}')
            project_node = next((node for node, _, _ in network.walk_states(self.node_id, strength=strength) if node.node_id == self.project_id), None)
            if project_node is None:
                raise ValueError('项目说明不可达')
            project = project_node.read({'method': 'key', 'key': 'content'})
            if project.status != 'ok':
                raise ValueError('项目说明读取失败')
            run_dir = self.file_path.parent / 'archive' / uuid4().hex
            run_dir.mkdir(parents=True)
            if self.file_path.exists() and self.file_path.read_bytes():
                raise ValueError('当前追加区有未归档发言，请先由宿主处理，不能覆盖已有记录')
            chain_token = call_chain.set((*chain, self.node_id))
            with self._lock:
                self.current_round = 0
                self.total_rounds = rounds

            def turn(member, message, *, discussion=False):
                node, remaining = states[member]
                budget['calls'] += 1
                token = current_access.set({'network': network, 'node_id': member, 'strength': remaining, 'visited': {member}})
                self._active_member = member if discussion else None
                self._turn_result = None
                completion_token = task_completion.set((lambda: self._turn_result) if discussion else None)
                try:
                    answer = node.agent.run(message, node=node, isolated=False)
                    if discussion and self._turn_result is None:
                        raise RuntimeError('成员未提交或跳过本轮')
                    return answer
                finally:
                    task_completion.reset(completion_token)
                    self._active_member = None
                    current_access.reset(token)
            for round_id in range(1, rounds + 1):
                with self._lock:
                    self.current_round = round_id
                snapshot = self._read_key('content')
                if snapshot.status != 'ok':
                    raise ValueError('黑板快照读取失败')
                for member in self.members:
                    message = f"项目任务：{task}\n项目说明：{project.items[0]['content']}\n本轮：{round_id}/{rounds}\n上一轮黑板：\n{snapshot.items[0]['content']}\n公共笔记节点：{self.notebook_id}；最终成果节点：{self.output_id}。自行安排最多10次模型请求，可读写私人笔记。必须在额度内调用submit_round提交公共黑板发言，或skip_round跳过。提交或跳过即结束本轮。"
                    turn(member, message, discussion=True)
                self._finish_round(run_dir / f'round_{round_id:03d}.md')
                completed = round_id
            output = next((node for node, _, _ in network.walk_states(self.node_id, strength=strength) if node.node_id == self.output_id), None)
            if not isinstance(output, TextFileNode):
                raise ValueError('输出黑板必须是可读的文本节点')

            def version():
                if not output.file_path.exists():
                    return None
                stat = output.file_path.stat()
                return (stat.st_mtime_ns, stat.st_ino, stat.st_size)
            before = version()
            summary = turn(self.recorder_id, f"讨论结束。项目任务：{task}\n最终讨论：\n{self._read_key('content').items[0]['content']}\n请整理公共笔记{self.notebook_id}，并通过已授权的工具将最终成果写入{self.output_id}。成功后说明完成情况；保留未决分歧。")
            if output.read({'method': 'key', 'key': 'content'}).status != 'ok' or version() == before:
                raise ValueError('输出黑板不可读或Recorder未成功保存成果')
            return NodeResult(items=[{'output_node_id': self.output_id, 'completed_rounds': completed, 'archive_path': str(run_dir), 'recorder_reply': summary}])
        except Exception as error:
            return NodeResult(status='error', errors=[str(error)], items=[{'completed_rounds': completed}])
        finally:
            if chain_token is not None:
                call_chain.reset(chain_token)
            if budget_token is not None:
                request_budget.reset(budget_token)
            self._discussion_lock.release()
