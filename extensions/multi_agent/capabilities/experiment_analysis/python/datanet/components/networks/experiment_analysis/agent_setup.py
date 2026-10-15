"""实验项目的 Agent 装配与原 CLI 入口。"""
import os
from dotenv import load_dotenv
from openai import OpenAI
from datanet.components.networks.experiment_analysis.paths import ENV_PATH
from datanet.abilities.agent_identity.configuration import assemble_agents
from datanet.components.networks.experiment_analysis.network_setup import build_lab_network

def build_agent_network(client, model: str):
    network, root = build_lab_network()
    assemble_agents(network, client, model_override=model)
    return (network, root)

def run_agent(user_message: str):
    load_dotenv(ENV_PATH)
    api_key = os.getenv('DEEPSEEK_API_KEY')
    model = os.getenv('DEEPSEEK_MODEL')
    if not api_key or not model:
        raise ValueError('请在 .env 中填写 API Key 和模型名称')
    client = OpenAI(api_key=api_key, base_url='https://api.deepseek.com', timeout=60.0, max_retries=0)
    try:
        _, root = build_agent_network(client, model)
        print('开始运行')
        answer = root.agent.run(user_message, node=root)
        print('收到回复：', answer)
        return answer
    finally:
        client.close()
