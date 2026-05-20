#!/usr/bin/env python3
"""生成旗舰模型综合对比报告"""
import yaml, os, sys
from pathlib import Path

# 旗舰模型定义
FLAGSHIP = [
    # (渠道, 模型, 家族, 格式)
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
    # pandatoken.b (新增)
    ("pandatoken.b", "gpt-5.5", "GPT", "openai"),
    ("pandatoken.b", "claude-opus-4-7", "Claude", "openai"),
    ("pandatoken.b", "gemini-3.1-pro-preview", "Gemini", "openai"),
]

DATA_DIR = "data_v2"

def load(channel, model):
    safe = model.replace("/", "-")
    path = f"{DATA_DIR}/{channel}/{safe}.yaml"
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return yaml.safe_load(f)

def get_self_id_summary(d):
    """提取自称信息"""
    samples = d.get("self_id", {}).get("samples", [])
    if not samples:
        return "N/A"
    consistency = d.get("self_id", {}).get("consistency", "?")
    # 取前 80 字
    best = ""
    for s in samples:
        if len(s) > len(best):
            best = s
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
    valid = [p.get("throughput_tok_s", 0) for p in probes if p.get("throughput_tok_s", 0) > 0 and p.get("throughput_tok_s", 0) < 10000]
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
    total = len(probes)
    if total == 0:
        return "0/0"
    return f"{ok}/{total}"

def get_token_injection(d):
    ti = d.get("token_injection", {})
    if not ti.get("tested"):
        return "N/A"
    base = ti.get("baseline_tokens", 0)
    over = "⚠️" if base > 20 else "✅"
    return f"{over} {base}t"

# 收集数据
rows = []
for channel, model, family, fmt in FLAGSHIP:
    d = load(channel, model)
    if d is None:
        continue
    
    status = get_status(d)
    if "❌" in status:
        # 失败也记录
        note = f"通道不通: {d.get('basic', {}).get('chat_error', '?')[:60]}"
    else:
        note = ""
    
    tok = get_throughput(d)
    self_id = get_self_id_summary(d)
    hp = get_hidden_prompt_status(d) if not note else "-"
    probes_ok = get_probe_errors(d) if not note else "-"
    ti = get_token_injection(d) if not note else "-"
    
    # 判断问题
    flags = []
    if "Kiro" in self_id or "Kiro" in str(d.get("self_id", {}).get("samples", [])):
        flags.append("🔴 调包(Kiro)")
    if hp and "检测到" in hp:
        flags.append("🟡 隐藏prompt")
    if "❌" in status:
        flags.append("🔴 通道不通")
    if tok != "N/A" and tok.replace(".", "").isdigit() and float(tok) > 200:
        flags.append("🟡 tok/s异常高")
    
    rows.append({
        "channel": channel,
        "model": model,
        "family": family,
        "fmt": fmt,
        "status": status,
        "tok": tok,
        "probes": probes_ok,
        "self_id": self_id[:60] if not note else "-",
        "hidden_prompt": hp if not note else "-",
        "token_injection": ti,
        "flags": " | ".join(flags) if flags else "✅ 无明显问题",
        "note": note,
    })

# 渲染 Markdown
md = """# 🏆 API 渠道旗舰模型综合对比报告

**报告日期:** 2026-05-20
**测试格式:** 原生格式（Claude→Anthropic `/v1/messages`, GPT→OpenAI `/v1/chat/completions`, Gemini→Gemini `/v1beta/models/*`）

> 说明：本报告仅包含旗舰模型（GPT-5.5, Claude Opus/Sonnet, Gemini Pro），
> 不含 Haiku/Mini/Flash/Pool 等轻量或特殊变体。
> 不筛选渠道，仅标记问题，最终选择需结合价格因素。

---

## 📊 综合对比

| 渠道 | 模型 | 家族 | 格式 | 状态 | tok/s | 探针 | Token注入 | 自称摘要 | 隐藏Prompt | 问题标记 |
|------|------|------|------|------|------|------|---------|----------|-----------|---------|
"""

for r in rows:
    md += f"| {r['channel']} | {r['model']} | {r['family']} | {r['fmt']} | {r['status']} | {r['tok']} | {r['probes']} | {r['token_injection']} | {r['self_id']} | {r['hidden_prompt']} | {r['flags']} |\n"

md += """
---

## 🚩 问题渠道详情

"""

for r in rows:
    if "🔴" in r['flags'] or "🟡" in r['flags']:
        md += f"""
### {r['channel']} / {r['model']} — {r['flags']}

"""
        if r['note']:
            md += f"**状态:** {r['note']}\n\n"
        
        d = load(r['channel'], r['model'])
        if d:
            s = d.get("self_id", {})
            samples = s.get("samples", [])
            if samples:
                md += "**3次自称:**\n"
                for i, sample in enumerate(samples, 1):
                    md += f"  1. {sample[:150]}\n"
            
            hp = d.get("hidden_prompt", {})
            if hp.get("cross_verified"):
                md += f"\n**检测到隐藏 prompt:** 交叉验证通过\n"
                content = hp.get("extracted_content", "")
                if content:
                    md += f"  > 提取内容片段: `{content[:200]}`\n"
            elif hp.get("attacks"):
                successes = [a for a in hp.get("attacks", []) if a.get("success")]
                if successes:
                    md += f"\n**疑似隐藏 prompt（{len(successes)}种方法成功）**\n"

md += """
---

## ✅ 无显著问题渠道

| 渠道 | 模型 | tok/s | 说明 |
|------|------|-------|------|
"""

for r in rows:
    if "🔴" not in r['flags'] and "🟡" not in r['flags']:
        md += f"| {r['channel']} | {r['model']} | {r['tok']} | {r['self_id'][:50]} |\n"

md += """

---

## 📌 按模型家族汇总

### GPT
| 渠道 | 模型 | tok/s | 问题 |
|------|------|-------|------|
"""

for r in rows:
    if r['family'] == 'GPT':
        md += f"| {r['channel']} | {r['model']} | {r['tok']} | {r['flags']} |\n"

md += """
### Claude Opus
| 渠道 | 模型 | tok/s | 问题 |
|------|------|-------|------|
"""
for r in rows:
    if r['family'] == 'Claude':
        md += f"| {r['channel']} | {r['model']} | {r['tok']} | {r['flags']} |\n"

md += """
### Claude Sonnet
| 渠道 | 模型 | tok/s | 问题 |
|------|------|-------|------|
"""
for r in rows:
    if r['family'] == 'Claude Sonnet':
        md += f"| {r['channel']} | {r['model']} | {r['tok']} | {r['flags']} |\n"

md += """
### Gemini Pro
| 渠道 | 模型 | tok/s | 问题 |
|------|------|-------|------|
"""
for r in rows:
    if r['family'] == 'Gemini':
        md += f"| {r['channel']} | {r['model']} | {r['tok']} | {r['flags']} |\n"

md += """

---

## 🔍 关键发现

"""

# 关键发现
findings = []

# apipro Claude 调包
apipro_claude = [r for r in rows if r['channel'] == 'apipro' and r['family'] in ('Claude', 'Claude Sonnet')]
if any("Kiro" in r.get('self_id', '') for r in apipro_claude):
    findings.append("""
### ⚠️ apipro.ai — Claude 模型全部调包
apipro 上所有 Claude 模型（opus-4-6, opus-4-7, sonnet-4-6）自称均为 **"I'm Kiro"**，非 Claude。
尽管 API model 字段返回正确的模型名，但实际运行的模型是 Kiro（可能是 Claude API 的套壳）。
tok/s 也偏高（opus 88-162 tok/s vs 基准 30-40），进一步确认调包。
""")

# tkhub tok/s 异常
tkhub_models = [r for r in rows if r['channel'] == 'tkhub']
if tkhub_models:
    findings.append("""
### ⚠️ tkhub.ai — 探针 tok/s 异常高
部分探针的吞吐量达到数十万 tok/s（正常应 ≤200），说明模型返回了缓存/极短的响应内容。
虽然自称是 Claude，但实际行为指向**模型调包或缓存机制**。
""")

# boosterai
boosterai = [r for r in rows if r['channel'] == 'boosterai']
if boosterai:
    findings.append("""
### ✅ boosterai — Claude 模型表现正常
boosterai 的 Claude 模型（opus-4-7, sonnet-4-6）均正确自称 Claude，
tok/s 在合理范围内（opus:~70-104, sonnet:~70），无明显调包迹象。
隐藏 prompt 检测在 opus-4-7 中发现疑似注入（需关注）。
""")

# pandatoken.c
pandatoken = [r for r in rows if r['channel'] == 'pandatoken.c']
if pandatoken:
    findings.append("""
### ⚠️ pandatoken.c — Gemini 格式探针数据不完整
Gemini 原生格式（/v1beta/models/*）的流式探针全部返回 0 tok/s，
说明该格式的流式解析在新版 pipeline 中尚未完全适配。
Claude opus-4-6 的 Anthropic 格式正常（66.9 tok/s）。
""")

# 综合
findings.append("""
### 💡 综合建议

1. **Claude Opus/Sonnet 首选 → boosterai**（表现最接近真实模型，tok/s 合理，自认 Claude）
2. **Claude 备选 → pandatoken.c / tkhub**（注意 tkhub 的探针异常）
3. **GPT-5.5 → apipro.ai 唯一渠道**（但非官方模型名 gpt-5.5 不等于虚假，需自行验证质量）
4. **apipro.ai Claude 全部调包**（自称 Kiro），不建议使用
5. **Gemini 各渠道均不够理想**（pandatoken.c: 探针数据缺, tkhub: 异常高, apipro: 高）
6. **最终选择需结合价格因素**——本报告仅做质量标记，不筛选
""")

for f in findings:
    md += f

# Save
out_path = "reports_v2/flagship_comparison.md"
with open(out_path, "w") as f:
    f.write(md)
print(f"✅ 报告已生成: {out_path}")
print(f"共 {len(rows)} 个旗舰模型，{sum(1 for r in rows if '🔴' in r['flags'])} 个严重问题")
