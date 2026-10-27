"""DeepSeek Chat Completions 的最小接入，只将模型报文交给 Agent 循环。

工具调用格式：https://api-docs.deepseek.com/guides/tool_calls/
"""

from pathlib import Path

from dotenv import dotenv_values
import httpx


class DeepSeekChat:
    def __init__(self, api_key: str, *, model: str = "deepseek-flash",
                 base_url: str = "https://api.deepseek.com") -> None:
        if not api_key:
            raise ValueError("未配置 DEEPSEEK_API_KEY")
        self._api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.requests: list[dict] = []

    @classmethod
    def from_env(cls, path: str | Path):
        values = dotenv_values(path)
        return cls(
            values.get("DEEPSEEK_API_KEY") or "",
            model=values.get("DEEPSEEK_MODEL") or "deepseek-flash",
            base_url=values.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com",
        )

    def __call__(self, messages: list, tools: list) -> dict:
        response = httpx.post(
            self.base_url + "/chat/completions",
            headers={"Authorization": "Bearer " + self._api_key},
            json={
                "model": self.model, "messages": messages, "tools": tools,
                "tool_choice": "auto", "stream": False,
                "thinking": {"type": "disabled"}, "temperature": 0, "max_tokens": 2048,
            },
            timeout=90,
        )
        if response.is_error:
            detail = response.text.replace(self._api_key, "[已隐藏密钥]")
            raise RuntimeError(f"DeepSeek API HTTP {response.status_code}: {detail}")
        body = response.json()
        choice = body["choices"][0]
        self.requests.append({
            "model": body.get("model"), "usage": body.get("usage"),
            "finish_reason": choice.get("finish_reason"),
        })
        if choice.get("finish_reason") == "length":
            raise RuntimeError("模型响应达到输出长度上限")
        return choice["message"]
