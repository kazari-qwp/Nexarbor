import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from config import ENV_PATH, SYSTEM_PROMPT_PATH, TOOLS_PATH
from labinsight.tools import TOOL_FUNCTIONS

def run_agent(user_message: str):
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    with TOOLS_PATH.open(encoding="utf-8") as file:
        tools = json.load(file)
    print("开始运行")
    # 将 .env 中的配置加载到环境变量
    load_dotenv(ENV_PATH)

    api_key = os.getenv("DEEPSEEK_API_KEY")
    model = os.getenv("DEEPSEEK_MODEL")

    if not api_key or not model:
        raise ValueError("请在 .env 中填写 API Key 和模型名称")

    # 创建客户端，指定请求发往 DeepSeek
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=60.0,
        max_retries=0,
    )
    for _ in range(5):
        # 这一行实际发送网络请求
        response = client.chat.completions.create(
            model=model,
            tools=tools,
            tool_choice="auto",
            messages=messages,
            extra_body={"thinking": {"type": "disabled"}},
            max_tokens=1000,
        )
        message = response.choices[0].message
        if not message.tool_calls:
            print("收到回复：", message.content)
            return message.content
        messages.append(message.model_dump(exclude_none=True))
        for tool_call in message.tool_calls:
            try:
                arguments = json.loads(tool_call.function.arguments)
                tool_name = tool_call.function.name
                if not isinstance(arguments, dict):
                    raise TypeError("工具参数必须是字典")

                tool_function = TOOL_FUNCTIONS.get(tool_name)

                if tool_function is None:
                    raise ValueError(f"未知工具：{tool_name}")

                result = tool_function(**arguments)

            except (ValueError, KeyError, TypeError) as error:
                result = {"error": str(error)}
            # 将执行结果返回给模型，并对应到这次调用
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })
    raise RuntimeError("工具调用达到 5 轮，尚未得到最终回复")
