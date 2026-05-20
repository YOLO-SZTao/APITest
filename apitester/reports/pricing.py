#!/usr/bin/env python3
"""获取各渠道定价并更新旗舰报告"""
import json, os, sys, yaml
from pathlib import Path
import urllib.request

CHANNELS = {
    "pandatoken.b": "https://b.pandatoken.net",
    "pandatoken.c": "https://c.pandatoken.net",
    "tkhub": "https://api.tkhub.ai",
    "boosterai": "https://ai.boosterai.cn",
}

FLAGSHIP_MODELS = [
    "gpt-5.5", "gpt-5.4",
    "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6",
    "gemini-3.1-pro-preview", "gemini-3.1-pro-high",
]

def fetch_pricing(url):
    try:
        r = urllib.request.urlopen(url, timeout=8)
        return json.loads(r.read())
    except:
        return None

# 收集定价
pricing = {}
for ch, base_url in CHANNELS.items():
    d = fetch_pricing(f"{base_url}/api/pricing")
    if not d:
        continue
    for m in d.get("data", []):
        name = m["model_name"]
        for t in FLAGSHIP_MODELS:
            if t in name:
                if ch not in pricing:
                    pricing[ch] = {}
                if name not in pricing[ch] or m.get("model_ratio", 0) > 0:
                    ratio = m.get("model_ratio", 0)
                    compl = m.get("completion_ratio", 1)
                    pricing[ch][name] = {
                        "input": ratio,
                        "output": round(ratio * compl, 4),
                        "completion_ratio": compl,
                        "cache": m.get("cache_ratio", 0),
                        "discount": m.get("discount", ""),
                    }

# 输出
print("=" * 100)
print(f"{'渠道':15s} {'模型':35s} {'input/1k':>10s} {'output/1k':>10s} {'倍率':>5s} {'折扣':>6s}")
print("-" * 100)
for ch in ["pandatoken.b", "pandatoken.c", "tkhub", "boosterai"]:
    if ch not in pricing:
        continue
    models = pricing[ch]
    # 按模型名排序（gpt, claude, gemini）
    for name in sorted(models.keys()):
        p = models[name]
        print(f"{ch:15s} {name:35s} {p['input']:>10.4f} {p['output']:>10.4f} {p['completion_ratio']:>4.1f}× {p['discount']:>6s}")

print(f"\n{'='*100}")
print("说明：单位为 credits/1k tokens。折扣如'9折'=9折优惠。")
print("apipro.ai 无定价接口，但实测 credit_usage 可推算。")
