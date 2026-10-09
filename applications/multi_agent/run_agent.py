import argparse
import os

from dotenv import load_dotenv
from openai import OpenAI
from config import ENV_PATH
from applications.multi_agent.setup import build_agent_network


def main():
    parser = argparse.ArgumentParser(description="父子 Agent 委托演示")
    parser.add_argument("question", nargs="?", default="请委托 worker 读取它的数字，并告诉我结果。")
    args = parser.parse_args()
    load_dotenv(ENV_PATH)
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("请在 .env 中填写 DEEPSEEK_API_KEY")
    with OpenAI(api_key=key, base_url="https://api.deepseek.com", timeout=60, max_retries=0) as client:
        _, root = build_agent_network(client, os.getenv("DEEPSEEK_MODEL"))
        print(root.invoke_agent(args.question))


if __name__ == "__main__":
    main()
