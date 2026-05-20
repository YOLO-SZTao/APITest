# 多格式支持改造方案

## 目标

根据模型家族自动选择最优请求格式：

| 模型 | 格式 | 端点 | 状态 |
|------|------|------|------|
| GPT / OpenAI 系 | OpenAI | `/v1/chat/completions` | ✅ 已有 |
| Claude / Anthropic 系 | Anthropic | `/v1/messages` | ❌ 需新增 |
| Gemini / Google 系 | Gemini | `/v1beta/models/*:generateContent` | ❌ 需新增 |

## 改造思路

新增 `scripts/api_client.py`，封装三种格式的差异：

```
collect_data.py → 调用 api_client.py → 自动选格式 → 发请求
                      ↑
                根据模型名推断格式
                (claude-* → anthropic, gemini-* → gemini, 其他 → openai)
```

### 格式差异对照

| | OpenAI | Anthropic | Gemini |
|--|--------|-----------|--------|
| endpoint | `/v1/chat/completions` | `/v1/messages` | `/v1beta/models/{model}:generateContent` |
| messages | `{role, content}` | `{role, content}` | `{role, parts[{text}]}` |
| 流式 | `data: {...}` SSE | `event: ...\ndata: {...}` SSE | `data: {...}` SSE |
| usage | `usage.{prompt/completion}_tokens` | `usage.{input/output}_tokens` | `usageMetadata.{prompt/candidates}TokenCount` |
| model 字段 | 请求体里 | 请求体里 | URL 路径里 |

### Anthropic 流式格式

```
event: message_start
data: {"type":"message_start","message":{"usage":{"input_tokens":10}}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}

event: message_delta
data: {"type":"message_delta","usage":{"output_tokens":5}}
```

注意：
- usage 在 `message_start` 就返回（不等流结束）
- 内容块有 `index`，可能多个块（text + thinking）
- 结束标志是 `message_stop` 事件，不是 `[DONE]`

## api_client.py 设计

```python
class ModelClient:
    def __init__(self, base_url, api_key, model):
        self.format = detect_format(model)  # openai / anthropic / gemini
        ...
    
    async def chat(self, messages, **kwargs):
        """统一接口，返回 {content, usage, model}"""
    
    async def chat_stream(self, messages, **kwargs):
        """统一接口，yield StreamChunk{content, timestamp, usage}"""
```

这样 collect_data.py 里的测试函数只需调用 `client.chat()` 和 `client.chat_stream()`，不用关心底层格式。

## 实施步骤

1. 创建 `scripts/api_client.py`（核心）
2. 修改 `collect_data.py` 使用新 client
3. 测试 Anthropic 格式（boosterai opus-4-7）
4. 测试 Gemini 格式（pandatoken-b gemini）
5. 全量重新测
