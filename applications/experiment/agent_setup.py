"""实验项目的 Agent 装配与原 CLI 入口。"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from config import ENV_PATH, SYSTEM_PROMPT_PATH, TOOLS_PATH
from datanet.agent import Agent
from applications.experiment.network_setup import build_lab_network


def build_agent_network(client, model: str):
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    with TOOLS_PATH.open(encoding="utf-8") as file:
        tool_definitions = json.load(file)
    network, root = build_lab_network()
    root.agent = Agent(
        client=client,
        model=model,
        system_prompt=system_prompt,
        tool_definitions=tool_definitions,
        extra_body={"thinking": {"type": "disabled"}},
    )
    root.set_agent_enabled(True)
    return network, root


def run_agent(user_message: str):
    load_dotenv(ENV_PATH)
    api_key = os.getenv("DEEPSEEK_API_KEY")
    model = os.getenv("DEEPSEEK_MODEL")
    if not api_key or not model:
        raise ValueError("请在 .env 中填写 API Key 和模型名称")

    # 客户端和业务配置由装配层提供，通用 Agent 不依赖 .env 路径。
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=60.0,
        max_retries=0,
    )
    try:
        _, root = build_agent_network(client, model)
        print("开始运行")
        answer = root.invoke_agent(user_message)
        print("收到回复：", answer)
        return answer
    finally:
        client.close()
