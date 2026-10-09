"""python -m applications.network_demo.run_agent [问题]；--local 不调用模型。"""

import argparse
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from config import ENV_PATH
from applications.network_demo.setup import build_agent_network, build_demo_network


def main():
    parser = argparse.ArgumentParser(description="数字网络 Agent 演示")
    parser.add_argument("question", nargs="?", default="从 n1 出发分别强读和弱读，列出数字并解释差异。")
    parser.add_argument("--local", action="store_true", help="直接调用工具，不请求模型")
    args = parser.parse_args()
    if args.local:
        _, root = build_demo_network()
        for name in ("describe_node", "weak_read", "strong_read"):
            arguments = {"node_id": "n1"}
            if name != "describe_node":
                arguments["key"] = "value"
            print(name)
            print(json.dumps(root.invoke_tool(name, **arguments), ensure_ascii=False, indent=2))
        return

    load_dotenv(ENV_PATH)
    api_key = os.getenv("DEEPSEEK_API_KEY")
    model = os.getenv("DEEPSEEK_MODEL")
    if not api_key or not model:
        raise ValueError("请在 .env 中填写 API Key 和模型名称")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=60.0, max_retries=0)
    try:
        _, root = build_agent_network(client, model)
        print(root.invoke_agent(args.question))
    finally:
        client.close()


if __name__ == "__main__":
    main()
