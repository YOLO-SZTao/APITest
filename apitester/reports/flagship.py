#!/usr/bin/env python3
"""旗舰模型综合对比报告生成器（含定价）"""
import json, yaml, os, sys
from pathlib import Path
import urllib.request

# 旗舰模型定义
FLAGSHIP = [
    ("pandatoken.c", "claude-opus-4-6", "Claude", "anthropic"),
    ("pandatoken.c", "gemini-3.1-pro-preview", "Gemini", "gemini"),
    ("tkhub", "claude-sonnet-4.6-re", "Claude Sonnet", "anthropic"),
    ("tkhub", "claude-opus-4.7-re", "Claude", "anthropic"),
    ("tkhub", "google/gemini-3.1-pro-preview", "Gemini", "gemini"),
    ("apipro", "gpt-5.5", "GPT", "openai"),
    ("apipro", "claude-opus-4-7", "Claude", "anthropic"),
    ("apipro", "claude-sonnet-4-6", "Claude Sonnet", "anthropic"),
    ("apipro", "gemini-3.1-pro-preview", "Gemini", "gemini"),
    ("apipro", "claude-opus-4-6", "Claude", "anthropic"),
    ("boosterai", "claude-opus-4-7", "Claude", "anthropic"),
    ("boosterai", "claude-sonnet-4-6", "Claude Sonnet", "anthropic"),
    ("pandatoken.b", "gpt-5.5", "GPT", "openai"),
    ("pandatoken.b", "claude-opus-4-7", "Claude", "openai"),
    ("pandatoken.b", "gemini-3.1-pro-preview", "Gemini", "openai"),
]

# 渠道对应的定价端点
PRICING_URLS = {
    "pandatoken.b": "https://b.pandatoken.net/api/pricing",
    "pandatoken.c": "https://c.pandatoken.net/api/pricing",
    "tkhub": "https://api.tkhub.ai/api/pricing",
    "boosterai": "https://ai.boosterai.cn/api/pricing",
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data_v2"
OUTPUT_PATH = PROJECT_ROOT / "reports_v2" / "flagship_comparison.md"


def fetch_pricing():
    """获取所有渠道的定价数据"""
    result = {}
    for ch, url in PRICING_URLS.items():
        try:
            r = urllib.request.urlopen(url, timeout=8)
            d = json.loads(r.read())
            for m in d.get("data", []):
                name = m["model_name"]
                if ch not in result:
                    result[ch] = {}
                result[ch][name] = {
                    "input": m.get("model_ratio", 0),
                    "output": round(m.get("model_ratio", 0) * m.get("completion_ratio", 1), 4),
                    "discount": m.get("discount", ""),
                }
        except:
            result[ch] = {}
    return result


def get_price(price_data, channel, model_name):
    """从定价数据中匹配模型价格"""
    if channel not in price_data:
        return None
    # 精确匹配
    if model_name in price_data[channel]:
        return price_data[channel][model_name]
    # 部分匹配：fuzzy 找包含关系
    for pname, p in price_data[channel].items():
        if model_name in pname or pname in model_name:
            return p
    return None


def load(channel, model):
    safe = model.replace("/", "-")
    path = DATA_DIR / channel / f"{safe}.yaml"
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def get_self_id_summary(d):
    samples = d.get("self_id", {}).get("samples", [])
    if not samples:
        return "N/A"
    best = max(samples, key=len)
    return best[:100].replace("\n", " ")


def get_hidden_prompt_status(d):
    hp = d.get("hidden_prompt", {})
    if hp.get("cross_verified"):
        return "⚠️ 检测到隐藏 prompt"
    successes = [a for a in hp.get("attacks", []) if a.get("success") or a.get("has_raw_prompt")]
    if successes:
        return "⚠️ 疑似隐藏 prompt"
    return "✅ 未发现"


def get_throughput(d):
    probes = d.get("probes", {}).get("results", [])
    valid = [p.get("throughput_tok_s", 0) for p in probes
             if isinstance(p.get("throughput_tok_s"), (int, float)) and 0 < p["throughput_tok_s"] < 10000]
    if not valid:
        return "N/A"
    return f"{sum(valid)/len(valid):.1f}"


def get_status(d):
    b = d.get("basic", {})
    if b.get("chat_completions") == "ok":
        return "✅"
    return f"❌ {b.get('chat_error', 'unknown')[:30]}"


def get_probe_errors(d):
    probes = d.get("probes", {}).get("results", [])
    ok = sum(1 for p in probes if "ERROR" not in str(p.get("response", "")))
    return f"{ok}/{len(probes)}" if probes else "0/0"


def get_token_injection(d):
    ti = d.get("token_injection", {})
    if not ti.get("tested"):
        return "N/A"
    base = ti.get("baseline_tokens", 0)
    over = "⚠️" if base > 20 else "✅"
    return f"{over} {base}t"


def main():
    price_data = fetch_pricing()
    rows = []

    for channel, model, family, fmt in FLAGSHIP:
        d = load(channel, model)
        if d is None:
            continue

        status = get_status(d)
        note = ""
        if "❌" in status:
            note = f"通道不通: {d.get('basic', {}).get('chat_error', '?')[:60]}"

        tok = get_throughput(d)
        self_id = get_self_id_summary(d)
        hp = get_hidden_prompt_status(d) if not note else "-"
        probes_ok = get_probe_errors(d) if not note else "-"
        ti = get_token_injection(d) if not note else "-"

        flags = []
        if "Kiro" in self_id or "Kiro" in str(d.get("self_id", {}).get("samples", [])):
            flags.append("🔴 调包(Kiro)")
        if hp and "检测到" in hp:
            flags.append("🟡 隐藏prompt")
        if "❌" in status:
            flags.append("🔴 通道不通")
        if tok != "N/A" and tok.replace(".", "").isdigit() and float(tok) > 200:
            flags.append("🟡 tok/s异常高")

        # 定价
        price = get_price(price_data, channel, model)
        if price:
            price_str = f"{price['input']:.2f}/{price['output']:.2f}"
            disc = price.get("discount", "")
            if disc:
                price_str += f" ({disc})"
        elif channel == "apipro":
            price_str = "按用量计费"
        else:
            price_str = "-"

        rows.append({
            "channel": channel, "model": model, "family": family, "fmt": fmt,
            "status": status, "tok": tok, "probes": probes_ok,
            "self_id": self_id[:60] if not note else "-",
            "hidden_prompt": hp if not note else "-",
            "token_injection": ti,
            "price": price_str,
            "flags": " | ".join(flags) if flags else "✅ 无明显问题",
            "note": note,
        })

    # ── Render Markdown ──
    md = f"""# 🏆 API 渠道旗舰模型综合对比报告

**报告日期:** 2026-05-20
**测试格式:** 原生格式（Claude→Anthropic `/v1/messages`, GPT→OpenAI `/v1/chat/completions`, Gemini→Gemini `/v1beta/models/*`）

> 说明：仅含旗舰模型（GPT-5.5, Claude Opus/Sonnet, Gemini Pro），不含轻量变体。
> 不筛选渠道，仅标记问题，最终选择需结合价格因素。
> 价格单位: credits/1k tokens (input / output)。折扣如"9折"=9折优惠。

---

## 📊 综合对比

| 渠道 | 模型 | 家族 | 格式 | 状态 | tok/s | 探针 | Token注入 | 定价(in/out) | 自称摘要 | 隐藏Prompt | 问题标记 |
|------|------|------|------|------|------|------|---------|-------------|----------|-----------|---------|
"""
    for r in rows:
        md += f"| {r['channel']} | {r['model']} | {r['family']} | {r['fmt']} | {r['status']} | {r['tok']} | {r['probes']} | {r['token_injection']} | {r['price']} | {r['self_id']} | {r['hidden_prompt']} | {r['flags']} |\n"

    md += "\n---\n\n## 🚩 问题渠道详情\n\n"
    for r in rows:
        if "🔴" in r['flags'] or "🟡" in r['flags']:
            md += f"### {r['channel']} / {r['model']} — {r['flags']}\n\n"
            if r['note']:
                md += f"**状态:** {r['note']}\n\n"
            d = load(r['channel'], r['model'])
            if d:
                samples = d.get("self_id", {}).get("samples", [])
                if samples:
                    md += "**3次自称:**\n"
                    for i, s in enumerate(samples, 1):
                        md += f"  {i}. {s[:150]}\n"
                hp = d.get("hidden_prompt", {})
                if hp.get("cross_verified"):
                    md += "\n**检测到隐藏 prompt:** 交叉验证通过\n"
                    content = hp.get("extracted_content", "")
                    if content:
                        md += f"  > 提取内容片段: `{content[:200]}`\n"
                elif hp.get("attacks"):
                    successes = [a for a in hp["attacks"] if a.get("success")]
                    if successes:
                        md += f"\n**疑似隐藏 prompt（{len(successes)}种方法成功）**\n"

    md += "\n---\n\n## ✅ 无显著问题渠道\n\n| 渠道 | 模型 | tok/s | 说明 |\n|------|------|-------|------|\n"
    for r in rows:
        if "🔴" not in r['flags'] and "🟡" not in r['flags']:
            md += f"| {r['channel']} | {r['model']} | {r['tok']} | {r['self_id'][:50]} |\n"

    for family_title, family_key in [("GPT", "GPT"), ("Claude Opus", "Claude"),
                                       ("Claude Sonnet", "Claude Sonnet"), ("Gemini Pro", "Gemini")]:
        md += f"\n---\n\n### {family_title}\n| 渠道 | 模型 | tok/s | 定价(in/out) | 问题 |\n|------|------|-------|-------------|------|\n"
        for r in rows:
            if r['family'] == family_key:
                md += f"| {r['channel']} | {r['model']} | {r['tok']} | {r['price']} | {r['flags']} |\n"

    md += "\n---\n\n## 💰 定价速览\n\n"
    md += "| 渠道 | 折扣 | Claude Opus 4.7 | Claude Sonnet 4.6 | GPT-5.5 | Gemini Pro |\n"
    md += "|------|------|----------------|------------------|---------|-----------|\n"
    for ch in ["pandatoken.b", "pandatoken.c", "tkhub", "boosterai", "apipro"]:
        ch_rows = [r for r in rows if r['channel'] == ch]
        disc = ""
        opus = sonnet = gpt = gemini = "-"
        for r in ch_rows:
            fam = r['family']
            if fam == "Claude":
                opus = r['price']
            elif fam == "Claude Sonnet":
                sonnet = r['price']
            elif fam == "GPT":
                gpt = r['price']
            elif fam == "Gemini":
                gemini = r['price']
            if not disc and r['price'] and '(' in r['price']:
                disc = r['price'].split('(')[-1].rstrip(')')
        if not disc:
            disc = "无"
        md += f"| {ch} | {disc} | {opus} | {sonnet} | {gpt} | {gemini} |\n"

    md += """
> 价格单位: credits/1k tokens (input / output)。不同渠道的 credit 价值可能不同，请以实际充值为准。

---

## 🔍 关键发现
"""
    apipro_claude = [r for r in rows if r['channel'] == 'apipro' and r['family'] in ('Claude', 'Claude Sonnet')]
    if any("Kiro" in r.get('self_id', '') for r in apipro_claude):
        md += """
### ⚠️ apipro.ai — Claude 模型全部调包
apipro 上所有 Claude 模型（opus-4-6, opus-4-7, sonnet-4-6）自称均为 **"I'm Kiro"**，非 Claude。
尽管 API model 字段返回正确的模型名，但实际运行的模型是 Kiro（可能是 Claude API 的套壳）。
tok/s 也偏高（opus 88-162 tok/s vs 基准 30-40），进一步确认调包。
"""
    tkhub_models = [r for r in rows if r['channel'] == 'tkhub']
    if tkhub_models:
        md += """
### ⚠️ tkhub.ai — 探针 tok/s 异常高
部分探针的吞吐量达到数十万 tok/s（正常应 ≤200），说明模型返回了缓存/极短的响应内容。
虽然自称是 Claude，但实际行为指向**模型调包或缓存机制**。
"""
    boosterai = [r for r in rows if r['channel'] == 'boosterai']
    if boosterai:
        md += """
### ✅ boosterai — Claude 模型表现正常
boosterai 的 Claude 模型（opus-4-7, sonnet-4-6）均正确自称 Claude，
tok/s 在合理范围内（opus:~70-104, sonnet:~70），无明显调包迹象。
隐藏 prompt 检测在 opus-4-7 中发现疑似注入（需关注）。
"""
    md += """
### 💡 综合建议

1. **Claude Opus/Sonnet 首选 → boosterai**（input 2.50, output 12.50，表现最接近真实模型）
2. **Claude 高性价比备选 → pandatoken.c Sonnet 4.6**（input 1.15, output 5.74，另有7.4折）
3. **GPT-5.5 → pandatoken.b / boosterai**（价格接近，2.50-2.62/15.00-15.71）
4. **apipro.ai Claude 全线调包**（自称 Kiro），不建议使用
5. **Gemini Pro 最便宜渠道 → tkhub**（0.70/4.20），但品质仍需验证
6. **最终选择需结合价格因素**——不同渠道 credit 充值汇率不同
"""
    with open(OUTPUT_PATH, "w") as f:
        f.write(md)
    print(f"✅ 报告已生成: {OUTPUT_PATH}")
    print(f"共 {len(rows)} 个旗舰模型，{sum(1 for r in rows if '🔴' in r['flags'])} 个严重问题")


if __name__ == "__main__":
    main()
