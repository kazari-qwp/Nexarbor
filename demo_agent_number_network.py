"""真实 API：Agent 读记忆，发现远端数字工具，原样返回该工具的响应。

直接运行：E:/miniconda3/python.exe -B -X utf8 demo_agent_number_network.py
只运行这一条端到端流程，不运行单元测试、对照实验或旧演示脚本。
"""

import json
from pathlib import Path

from app.agent_loop import MinimalAgentLoop
from adapt.models.deepseek import DeepSeekChat
from domain.core import access
from domain.agent import MarkdownAgentNode
from domain.core import Link
from domain.core import MarkdownNode
from domain.core import Module
from domain.core import Network
from domain.core import NodeInfo
from domain.core import CallableTool
from modules.tool_discovery import ToolDiscoveryModule


ROOT = Path(__file__).resolve().parent
DIRECTORY = ROOT / 'demo_data' / 'agent_numbers'
INITIAL_INPUT = '读取记忆，获得指令。'
MEMORY = '使用工具，并原样返回结果（不要做任何测试）。'
NUMBERS = {
    'numbers_root': 11, 'number_left': 23, 'number_right': 47,
    'number_merge': 89, 'number_far': 131,
    'number_blocked': 173, 'number_blue': 211,
}


class NumberReader(Module):
    def __init__(self):
        super().__init__('number_reader', channels='a', strength=2)
        self.tools._add(CallableTool(
            'read_numbers', self.read_numbers,
            description='读取数字网络。以此工具所在节点为起点，按频道 a、强度 2 返回节点 ID 到数字的 JSON 对象。',
            parameters={'type': 'object', 'properties': {}, 'additionalProperties': False},
            modules=(self,),
        ))

    @access()
    def _read_number(self, node):
        return int(node.dataer.read().strip())

    def read_numbers(self):
        return self._read_number()


def build_network(runner):
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    memory_path = DIRECTORY / 'memory.md'
    memory_path.write_text(MEMORY, encoding='utf-8')
    agent_node = MarkdownAgentNode(NodeInfo('agent', '记忆 Agent'), memory_path, save_data=False, runner=runner)
    nodes = {'agent': agent_node}
    for node_id, value in NUMBERS.items():
        path = DIRECTORY / f'{node_id}.md'
        path.write_text(str(value), encoding='utf-8')
        nodes[node_id] = MarkdownNode(NodeInfo(node_id, node_id), path, save_data=False)
    for node in nodes.values():
        node.bias = -1

    # 发现工具只走 tools 频道；数字工具只走 a 频道。
    agent_node.links.add(Link('numbers_root', 'tools'))
    for source, target, channel in [
        ('numbers_root', 'number_left', 'a'),
        ('numbers_root', 'number_right', 'a'),
        ('numbers_root', 'number_blue', 'b'),
        ('number_left', 'number_merge', 'a'),
        ('number_right', 'number_merge', 'a'),
        ('number_merge', 'number_far', 'a'),
        ('number_far', 'number_blocked', 'a'),
    ]:
        nodes[source].links.add(Link(target, channel))

    reader = NumberReader()
    nodes['numbers_root'].install(reader)
    agent_node.install(ToolDiscoveryModule(channels='tools', strength=2))
    return Network(nodes.values()), agent_node


def main():
    model = DeepSeekChat.from_env(ROOT / '.env')
    loop = MinimalAgentLoop(model)
    network, agent = build_network(loop.run)
    report = {'model': model.model, 'initial_input': INITIAL_INPUT, 'memory': MEMORY}
    print('模型:', model.model, flush=True)
    print('初始指令:', INITIAL_INPUT, flush=True)
    try:
        output = agent.run(INITIAL_INPUT)
        expected = {key: NUMBERS[key] for key in (
            'numbers_root', 'number_left', 'number_right', 'number_merge', 'number_far',
        )}
        call_names = [call['name'] for call in loop.tool_calls]
        number_calls = [call for call in loop.tool_calls if call['name'] == 'read_numbers']
        tool_output = number_calls[-1]['result'] if number_calls else None
        checks = {
            '先读记忆再调用数字工具': (
                'memory_query' in call_names and 'read_numbers' in call_names
                and call_names.index('memory_query') < call_names.index('read_numbers')
            ),
            '结果是工具节点出发的数字网络': (
                tool_output is not None and json.loads(tool_output) == expected
            ),
            '模型最终回答与工具响应逐字一致': output == tool_output,
        }
        report.update(output=output, checks=checks, passed=all(checks.values()))
        print('工具调用:', ' -> '.join(call_names), flush=True)
        print('最终回答:', output, flush=True)
        print('结果核对:', json.dumps(checks, ensure_ascii=False), flush=True)
    except Exception as error:
        report.update(passed=False, error=str(error))
        raise
    finally:
        report.update(
            tool_names=loop.tool_names, tool_calls=loop.tool_calls,
            messages=loop.messages, api_requests=model.requests,
        )
        path = DIRECTORY / 'run.json'
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('完整调用记录:', path, flush=True)
    if not report['passed']:
        raise RuntimeError('真实 Agent 链路的结果未满足预期，请查看 run.json')


if __name__ == '__main__':
    main()
