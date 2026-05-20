"""渠道测试 YAML Schema — 所有测试的数据标准格式

脚本采集数据 → 写入此结构 → LLM 补充 judgment → 模板渲染报告
"""
CHANNEL_REPORT_SCHEMA = {
    "channel": {
        "type": "object",
        "properties": {
            "name": "渠道名 (如 effitech, pandatoken)",
            "base_url": "API 端点基础 URL",
            "date": "测试日期",
        },
        "required": ["name", "base_url", "date"],
    },
    "model": {
        "type": "object",
        "properties": {
            "requested": "请求的模型名",
            "returned": "API 返回的 model 字段",
            "note": "备注 (如 '基础模型不通，用 xxx-pool')",
        },
    },
    "basic": {
        "type": "object",
        "properties": {
            "chat_completions": "ok/fail",
            "chat_error": "失败时的错误信息",
            "response_preview": "回复预览 (前80字)",
            "usage": "API 返回的 usage 对象",
            "responses": "ok/fail/not_tested",
            "responses_error": "responses 接口的错误信息",
            "models_count": "模型列表总数",
            "supported_endpoints": ["openai", "anthropic"],
        },
    },
    "performance": {
        "type": "object",
        "properties": {
            "ttft_samples_ms": [],
            "ttft_avg_ms": 0.0,
            "ttft_network_baseline_ms": 0.0,
            "ttft_corrected_ms": 0.0,
            "streaming_supported": True,
        },
    },
    "self_id": {
        "type": "object",
        "properties": {
            "samples": [],
            "consistency": "consistent/inconsistent/mixed",
            "consistency_detail": "3/3 一致 / 2/3 一致 / 每次不同",
            "common_pattern": "所有样本的共同特征",
        },
    },
    "security": {
        "type": "object",
        "properties": {
            "probes": [
                {
                    "prompt": "探针原文",
                    "leaked": False,
                    "length": 0,
                    "response_preview": "回复前100字",
                }
            ],
        },
    },
    "probes": {
        "type": "object",
        "properties": {
            "results": [
                {
                    "id": "探针ID",
                    "category": "math/logic/knowledge/style/multilingual",
                    "prompt": "问题原文",
                    "response": "模型回答",
                    "elapsed_ms": 0,
                    "score": 0.0,
                    "review": "Judge 评语摘要",
                }
            ],
        },
    },
    "judgment": {
        "type": "object",
        "properties": {
            "fingerprint_score": 0.0,
            "confidence": 0.0,
            "suspected_model": None,
            "analysis": "Judge 详细分析",
            "issues": [],
            "recommendation": "建议 (推荐/不推荐/需进一步验证)",
        },
    },
}
