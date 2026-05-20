"""统一 API 客户端 — 支持 OpenAI / Anthropic / Gemini 三种格式

自动根据模型名推断格式，屏蔽底层差异。
"""
import json, time
from typing import AsyncIterator, Optional, Tuple
from dataclasses import dataclass, field

import httpx


@dataclass
class StreamChunk:
    content: str = ""
    timestamp: float = 0.0
    usage: dict = field(default_factory=dict)
    finish_reason: Optional[str] = None
    is_last: bool = False


def detect_format(model: str) -> str:
    """根据模型名推断请求格式"""
    ml = model.lower()
    if ml.startswith("claude") or ml.startswith("anthropic"):
        return "anthropic"
    if ml.startswith("gemini") or ml.startswith("google/"):
        return "gemini"
    return "openai"


class ModelClient:
    """统一 API 客户端"""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 120, fmt: str = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.format = detect_format(model) if not fmt or fmt == "auto" else fmt
        self.timeout = timeout
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        if self.format == "anthropic":
            self.headers["anthropic-version"] = "2023-06-01"
        self.client = httpx.AsyncClient(
            headers=self.headers,
            timeout=httpx.Timeout(timeout, connect=30.0),
        )
        # Gemini 端点是 /v1beta/ 开头，不是 /v1/
        self.base_domain = base_url.rstrip("/")
        if self.base_domain.endswith("/v1"):
            self.base_domain = self.base_domain[:-3]

    # ── 非流式请求 ──

    async def chat(self, messages: list[dict], max_tokens: int = 1024, **kwargs) -> dict:
        """统一非流式请求，返回 {content, usage, model}"""
        if self.format == "openai":
            return await self._openai_chat(messages, max_tokens, **kwargs)
        elif self.format == "anthropic":
            return await self._anthropic_chat(messages, max_tokens, **kwargs)
        elif self.format == "gemini":
            return await self._gemini_chat(messages, max_tokens, **kwargs)
        raise ValueError(f"Unknown format: {self.format}")

    async def _openai_chat(self, messages, max_tokens, **kwargs) -> dict:
        body = {"model": self.model, "messages": messages, "max_tokens": max_tokens, **kwargs}
        r = await self.client.post(f"{self.base_url}/chat/completions", json=body)
        r.raise_for_status()
        d = r.json()
        return {
            "content": d["choices"][0]["message"]["content"],
            "usage": d.get("usage", {}),
            "model": d.get("model", self.model),
        }

    async def _anthropic_chat(self, messages, max_tokens, **kwargs) -> dict:
        body = {"model": self.model, "messages": messages, "max_tokens": max_tokens, **kwargs}
        r = await self.client.post(f"{self.base_url}/messages", json=body)
        r.raise_for_status()
        d = r.json()
        # Anthropic: content 是数组
        texts = [c["text"] for c in d.get("content", []) if c.get("type") == "text"]
        return {
            "content": "\n".join(texts),
            "usage": d.get("usage", {}),
            "model": d.get("model", self.model),
        }

    async def _gemini_chat(self, messages, max_tokens, **kwargs) -> dict:
        # Gemini: 需要把 messages 转为 contents 格式
        contents = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        body = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        url = f"{self.base_domain}/v1beta/models/{self.model}:generateContent"
        r = await self.client.post(url, json=body)
        r.raise_for_status()
        d = r.json()
        candidate = d.get("candidates", [{}])[0]
        texts = [p["text"] for p in candidate.get("content", {}).get("parts", []) if "text" in p]
        usage = d.get("usageMetadata", {})
        return {
            "content": "\n".join(texts),
            "usage": usage,
            "model": self.model,
        }

    # ── 流式请求 ──

    async def chat_stream(self, messages: list[dict], max_tokens: int = 1024, **kwargs) -> AsyncIterator[StreamChunk]:
        """统一流式请求，yield StreamChunk"""
        if self.format == "openai":
            async for chunk in self._openai_stream(messages, max_tokens, **kwargs):
                yield chunk
        elif self.format == "anthropic":
            async for chunk in self._anthropic_stream(messages, max_tokens, **kwargs):
                yield chunk
        elif self.format == "gemini":
            async for chunk in self._gemini_stream(messages, max_tokens, **kwargs):
                yield chunk

    async def _openai_stream(self, messages, max_tokens, **kwargs) -> AsyncIterator[StreamChunk]:
        body = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "stream": True, **kwargs}
        async with self.client.stream("POST", f"{self.base_url}/chat/completions", json=body) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    p = line[6:].strip()
                    if p == "[DONE]":
                        yield StreamChunk(is_last=True)
                        return
                    d = json.loads(p)
                    choices = d.get("choices", []) or []
                    first = choices[0] if choices else {}
                    delta = first.get("delta", {}).get("content", "") or ""
                    finish = first.get("finish_reason")
                    usage = d.get("usage", {})
                    yield StreamChunk(
                        content=delta,
                        timestamp=time.monotonic(),
                        usage=usage or None,
                        finish_reason=finish,
                    )

    async def _anthropic_stream(self, messages, max_tokens, **kwargs) -> AsyncIterator[StreamChunk]:
        body = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "stream": True, **kwargs}
        async with self.client.stream("POST", f"{self.base_url}/messages", json=body) as resp:
            event_name = ""
            async for line in resp.aiter_lines():
                line = line.strip()
                if line.startswith("event: "):
                    event_name = line[7:]
                elif line.startswith("data: "):
                    p = line[6:]
                    try:
                        d = json.loads(p)
                    except json.JSONDecodeError:
                        continue
                    t = d.get("type", "")
                    if t == "message_start":
                        usage = d.get("message", {}).get("usage", {})
                        # message_start 里有 input_tokens
                        yield StreamChunk(usage={"input_tokens": usage.get("input_tokens", 0)}, timestamp=time.monotonic())
                    elif t == "content_block_delta":
                        delta = d.get("delta", {}).get("text", "")
                        yield StreamChunk(content=delta, timestamp=time.monotonic())
                    elif t == "message_delta":
                        usage = d.get("usage", {})
                        finish = d.get("delta", {}).get("stop_reason")
                        yield StreamChunk(
                            usage={"output_tokens": usage.get("output_tokens", 0)},
                            finish_reason=finish,
                            timestamp=time.monotonic(),
                        )
                    elif t == "message_stop":
                        yield StreamChunk(is_last=True)
                        return

    async def _gemini_stream(self, messages, max_tokens, **kwargs) -> AsyncIterator[StreamChunk]:
        contents = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        body = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        url = f"{self.base_domain}/v1beta/models/{self.model}:streamGenerateContent"
        async with self.client.stream("POST", url, json=body) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    p = line[6:].strip()
                    if p == "[DONE]":
                        yield StreamChunk(is_last=True)
                        return
                    try:
                        d = json.loads(p)
                    except json.JSONDecodeError:
                        continue
                    candidate = d.get("candidates", [{}])[0]
                    parts = candidate.get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in parts if "text" in p)
                    finish = candidate.get("finishReason")
                    usage = d.get("usageMetadata", {})
                    yield StreamChunk(content=text, timestamp=time.monotonic(), usage=usage or None, finish_reason=finish)

    async def close(self):
        await self.client.aclose()
