"""一次真实API验证，保留工具轨迹与确定性统计对照，不改原数据。"""
import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv
from openai import OpenAI
from datanet.components.networks.creation_validation.paths import PROJECT_ROOT, ENV_PATH, COMPONENTS_DIR
from datanet.core.network import Network
from datanet.core.component_registry import component_root, resource_directory
from datanet.core.agent_node import AgentNode
from datanet.abilities.agent_identity.configuration import assemble_agents
from datanet.core.node_creation import attach_node_creation_tools
from datanet.abilities.agent_identity.creation import attach_agent_creation_tools
from datanet.core.serialization import save_network
from datanet.components.networks.experiment_analysis.toolkit import TOOLKITS
from datanet.components.networks.experiment_analysis.network_setup import build_lab_network

def tool_results(agent):
    return [json.loads(message['content']) for message in agent.messages if message['role'] == 'tool']

def run():
    load_dotenv(ENV_PATH)
    key = os.getenv('DEEPSEEK_API_KEY')
    model = os.getenv('DEEPSEEK_MODEL')
    if not key or not model:
        raise ValueError('项目.env缺少模型配置')
    directory = PROJECT_ROOT / '.models' / 'research' / 'creation_validation' / uuid4().hex
    directory.mkdir(parents=True)
    agent_source = component_root() / 'nodes/agent_experiment_report/python/datanet/components/agents/experiment_report'
    package = json.loads((agent_source / 'package.json').read_text(encoding='utf-8'))
    package['config']['model'] = model
    for field in ('prompt_path', 'tools_path'):
        package['config'][field] = str(agent_source / package['config'][field])
    agent_package = directory / 'agent_package.json'
    agent_package.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding='utf-8')
    network = Network()
    root = AgentNode('coordinator', '验证根节点', file_path=directory/'root-memory.md')
    network.add_node(root)
    report = {'model': model, 'directory': str(directory), 'success': False}
    client = OpenAI(api_key=key, base_url='https://api.deepseek.com', timeout=90, max_retries=0)
    model_calls = []
    original_create = client.chat.completions.create

    def traced_create(**request):
        response = original_create(**request)
        model_calls.append({'messages': deepcopy(request['messages']), 'response': response.choices[0].message.model_dump(exclude_none=True)})
        return response
    client.chat.completions.create = traced_create
    try:
        attach_node_creation_tools(network, root, storage_dir=directory / 'nodes', scope='descendants', network_presets={'experiment': component_root() / 'network_presets/experiment_analysis/python/datanet/components/networks/experiment_analysis/package.json'}, toolkits=TOOLKITS)
        attach_agent_creation_tools(network, root, storage_dir=directory / 'agents', client=client, presets={'experiment_report': agent_package}, scope='descendants')
        root.agent_config = {'model': model, 'prompt_path': str(resource_directory(__file__) / 'prompt.md'), 'tools_path': None, 'max_rounds': 12, 'max_tokens': 1800, 'thinking': False, 'node_bindings': {}, 'max_signal_strength': 3}
        assemble_agents(network, client, node_ids={root.node_id})
        print('根Agent开始选择预设、创建子网络、挂载子Agent并委托分析', flush=True)
        report['answer'] = root.agent.run('查询项目A的有效样本数、通过数、失败数、合格率，以及实际使用的规则和数据来源。', node=root)
        root_calls = [call['function']['name'] for message in root.agent.messages for call in message.get('tool_calls', [])]
        required = {'list_node_presets', 'list_agent_presets', 'create_network', 'create_agent', 'ask_agent'}
        if not required <= set(root_calls):
            raise AssertionError(f'根Agent未完成必要链路：{sorted(required - set(root_calls))}')
        children = [node for node in network.nodes.values() if node is not root and node.agent is not None]
        if len(children) != 1:
            raise AssertionError('未恰好创建一个子Agent')
        child = children[0]
        feedback = tool_results(root.agent)
        if any((isinstance(result, dict) and ('error' in result or result.get('status', 'ok') != 'ok') for result in feedback)):
            raise AssertionError('根Agent工具调用存在失败')
        child_calls = [call for call in model_calls if call['messages'][0]['content'] == child.agent.system_prompt]
        if not child_calls:
            raise AssertionError('没有实际请求子Agent模型')
        child_history = child_calls[-1]['messages']
        analysis_ids = {call['id'] for message in child_history for call in message.get('tool_calls', []) if call['function']['name'] == 'analyze_project'}
        actual_results = [json.loads(message['content']) for message in child_history if message['role'] == 'tool' and message['tool_call_id'] in analysis_ids]
        if len(actual_results) != 1 or 'pass_rate' not in actual_results[0]:
            raise AssertionError('子Agent未成功调用一次真实实验分析工具')
        actual = actual_results[0]
        _, original_root = build_lab_network()
        expected = original_root.invoke_tool('analyze_project', project_id='A')
        keys = ('project_id', 'valid_count', 'passed_count', 'failed_count', 'pass_rate', 'rule')
        if any((name not in actual or actual[name] != expected[name] for name in keys)):
            raise AssertionError('新网络统计与原实验网络不一致')
        if child.agent.prompt_path == agent_source / 'prompt.md':
            raise AssertionError('子Agent错误共享预设提示词')
        if 'create_network' in child.tools or 'create_agent' in child.tools:
            raise AssertionError('子Agent错误继承创建能力')
        save_network(network, directory / 'network.json')
        report.update(success=True, root_tool_calls=root_calls, statistics=actual, expected_statistics=expected, child_node_id=child.node_id, child_prompt_path=str(child.agent.prompt_path))
        print(report['answer'], flush=True)
        print('链路验证通过；结果目录：' + str(directory), flush=True)
        return report
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if root.agent is not None:
            report['root_messages'] = root.agent.messages
        report['model_calls'] = model_calls
        (directory / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        client.close()
if __name__ == '__main__':
    run()
