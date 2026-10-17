"""根Agent真实创建五人组，两轮提交测试，Recorder保存成功。"""
import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv
from openai import OpenAI
from datanet.components.networks.discussion_group.paths import PROJECT_ROOT, COMPONENTS_DIR, ENV_PATH
from datanet.core.agent_node import AgentNode
from datanet.core.network import Network
from datanet.core.component_registry import component_root
from datanet.abilities.agent_identity.configuration import assemble_agents
from datanet.core.node_creation import attach_node_creation_tools
from datanet.abilities.agent_identity.creation import attach_agent_creation_tools
from datanet.components.networks.discussion_group.setup import PACKAGE_PATH, storage_toolkits

def run():
    load_dotenv(ENV_PATH)
    directory = PROJECT_ROOT / '.models' / 'research' / 'discussion_validation' / uuid4().hex
    directory.mkdir(parents=True)
    client = OpenAI(api_key=os.environ['DEEPSEEK_API_KEY'], base_url='https://api.deepseek.com', timeout=90, max_retries=0)
    model = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')
    report = {'success': False, 'directory': str(directory), 'model_calls': []}
    original = client.chat.completions.create

    def traced(**request):
        response = original(**request)
        report['model_calls'].append({'messages': deepcopy(request['messages']), 'response': response.choices[0].message.model_dump(exclude_none=True)})
        print(f"模型请求 {len(report['model_calls'])} 完成", flush=True)
        return response
    client.chat.completions.create = traced
    network = Network()
    root = AgentNode('root', '测试根Agent', file_path=directory/'root-memory.md')
    network.add_node(root)
    group = json.loads(PACKAGE_PATH.read_text(encoding='utf-8'))
    presets = {}
    for name in ('discussion_leader', 'discussion_recorder', 'discussion_member'):
        source = component_root() / ('nodes/agent_' + name) / 'python/datanet/components/agents' / name
        document = json.loads((source / 'package.json').read_text(encoding='utf-8'))
        document['config']['model'] = model
        for key in ('prompt_path', 'tools_path'):
            document['config'][key] = str(source / document['config'][key])
        path = directory / (name + '.json')
        path.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
        presets[name] = path
    for node in group['network']['nodes']:
        if node['agent']:
            node['agent']['package'] = str(presets[Path(node['agent']['package']).name])
    group_path = directory / 'group.json'
    group_path.write_text(json.dumps(group, ensure_ascii=False), encoding='utf-8')
    registry = storage_toolkits(directory / 'data')
    install = registry['discussion_group_storage']

    def install_test(network, board):
        install(network, board)
        network.nodes[board.project_id].write('content', '最小链路测试：所有五名成员每轮只调用submit_round(content="测试")，content必须恰好是两个汉字测试，不加角色、说明或标点，共两轮。不要跳过。Recorder在讨论结束后向最终成果节点写入成功，最后正文也只回复成功。')
    registry['discussion_group_storage'] = install_test
    prompt = directory / 'root_prompt.md'
    prompt.write_text('你负责执行真实测试。先调用create_network，preset=group，instance_id=team，entry_point=board，with_agents=true。之后对返回的board入口调用list_tools，strength=3；然后invoke_tool调用run_discussion，strength=3，arguments包含rounds=2，task必须明确为：所有五名成员每轮调用submit_round(content="测试")，content必须恰好等于测试这两个汉字，不加其他内容，不跳过，共两轮；Recorder结束后向成果节点写入成功，并只回复成功。不要再额外委托成员。工具完成后只回复成功，若失败如实报告。', encoding='utf-8')
    try:
        attach_node_creation_tools(network, root, storage_dir=directory / 'nodes', scope='descendants', network_presets={'group': group_path}, toolkits=registry)
        attach_agent_creation_tools(network, root, storage_dir=directory / 'agents', presets=presets, client=client, scope='descendants')
        root.agent_config = dict(model=model, prompt_path=str(prompt), tools_path=None, max_rounds=10, max_tokens=1200, thinking=False, node_bindings={}, max_signal_strength=3)
        assemble_agents(network, client, node_ids={root.node_id})
        report['root_reply'] = root.agent.run('开始两轮测试。', node=root)
        boards = [node for node in network.nodes.values() if hasattr(node, 'members')]
        if len(boards) != 1:
            raise AssertionError('未创建一个讨论小组')
        board = boards[0]
        archives = list((board.file_path.parent / 'archive').glob('*/round_*.md'))
        if len(archives) != 2:
            raise AssertionError(f'归档轮数错误：{len(archives)}')
        for path in archives:
            text = path.read_text(encoding='utf-8')
            if text.count('\n## 第') != 5 or text.count('\n测试\n') != 5:
                raise AssertionError('本轮不是五人各提交一次测试')
        output = network.nodes[board.output_id].file_path.read_text(encoding='utf-8').strip()
        recorder = network.nodes[board.recorder_id].agent
        if output != '成功' or recorder.messages[-1].get('content', '').strip() != '成功':
            raise AssertionError('Recorder未保存并返回成功')
        root_calls = [call['function']['name'] for message in root.agent.messages for call in message.get('tool_calls', [])]
        if not {'create_network', 'invoke_tool'} <= set(root_calls):
            raise AssertionError('根Agent未通过创建和调用工具完成任务')
        report.update(success=True, output=output, archives=[str(p) for p in archives], root_tool_calls=root_calls)
        print('真实API测试成功；报告：' + str(directory / 'report.json'), flush=True)
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['root_messages'] = root.agent.messages if root.agent else []
        (directory / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        client.close()
if __name__ == '__main__':
    run()
