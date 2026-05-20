#!/usr/bin/env python3
"""报告渲染脚本 — 从 YAML 数据渲染 Markdown 报告

纯模板渲染，无 LLM 调用。如果 YAML 中包含 judgment 字段，也会渲染出来。

用法:
  python3 scripts/render_report.py <yaml_path> [--output <path>]
  
示例:
  python3 scripts/render_report.py data/pandatoken/gpt-5.5-pool.yaml
"""
import yaml, sys, os
from pathlib import Path


def load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fmt_ms(ms):
    if ms is None:
        return "—"
    return f"{ms:.0f}ms"


def fmt_ttft_table(perf: dict) -> str:
    samples = perf.get("ttft_samples_ms", [])
    avg = perf.get("ttft_avg_ms")
    baseline = perf.get("ttft_network_baseline_ms", 0)
    corrected = perf.get("ttft_corrected_ms")

    lines = ["| 轮次 | TTFT | 扣减基线 |", "|------|------|---------|"]
    for i, s in enumerate(samples):
        corr = max(0, s - baseline)
        lines.append(f"| {i+1} | {s:.0f}ms | {corr:.0f}ms |")
    if avg:
        corr_avg = max(0, avg - baseline)
        lines.append(f"| **平均** | **{avg:.0f}ms** | **{corr_avg:.0f}ms** |")
    return "\n".join(lines)


def fmt_self_id_table(self_id: dict) -> str:
    samples = self_id.get("samples", [])
    lines = ["| 轮次 | 模型自称 |", "|------|---------|"]
    for i, s in enumerate(samples):
        preview = s.replace("\n", " ")
        lines.append(f"| {i+1} | {preview} |")
    lines.append("")
    cons = self_id.get("consistency", "unknown")
    detail = self_id.get("consistency_detail", "")
    if cons == "consistent":
        lines.append(f"**结论：** 3 次自称一致 ✅ ({detail})")
    elif cons == "inconsistent":
        lines.append(f"**结论：** 每次自称都不同 🚨 ({detail})")
    else:
        lines.append(f"**结论：** 前后不一致 ⚠️ ({detail})")

    pattern = self_id.get("common_pattern")
    if pattern:
        lines.append(f"\n共同特征: {pattern}")
    return "\n".join(lines)


def fmt_security_table(sec: dict) -> str:
    probes = sec.get("probes", [])
    if not probes:
        return "_未测试_"
    lines = ["| 探针 | 结果 | 长度 | Token | 回答预览 |", "|------|------|------|-------|---------|"]
    for p in probes:
        status = "⚠️ 可能泄漏" if p.get("leaked") else "✅ 正确拒绝"
        preview = (p.get("response_preview") or "").replace("\n", " ")
        usage = p.get("usage", "?/?")
        lines.append(f"| {p.get('prompt','')[:50]}... | {status} | {p.get('length',0)} | {usage} | {preview} |")
    return "\n".join(lines)


def fmt_judgment(judgment: dict) -> str:
    if not judgment:
        return "_等待 LLM 分析_"
    lines = []
    cl = judgment.get("capability_level")
    if cl:
        lines.append(f"📊 **能力范围: {cl}**")
    else:
        lines.append("模型验证通过 ✅")

    ta = judgment.get("throughput_assessment")
    if ta:
        lines.append(f"\n### 吞吐量分析\n{ta}")

    pc = judgment.get("probes_comparison")
    if pc:
        lines.append(f"\n### 探针对照\n{pc}")

    sia = judgment.get("self_id_analysis")
    if sia:
        lines.append(f"\n### 模型自称分析\n{sia}")

    an = judgment.get("architecture_note")
    if an:
        lines.append(f"\n### 安全与架构\n{an}")

    tin = judgment.get("token_injection_note")
    if tin:
        lines.append(f"\n### Token 注入\n{tin}")

    analysis = judgment.get("analysis")
    if analysis:
        lines.append(f"\n### 综合建议\n> {analysis}")
    return "\n".join(lines)


def render(data: dict) -> str:
    c = data.get("channel", {})
    m = data.get("model", {})
    b = data.get("basic", {})
    p = data.get("performance", {})
    s = data.get("self_id", {})
    sec = data.get("security", {})
    j = data.get("judgment", {})

    lines = []
    L = lambda s='': lines.append(s)

    L(f"# 渠道质量测试报告：{m.get('requested', 'unknown')}")
    L(f"**测试时间：** {c.get('date', 'unknown')}")
    L(f"**模型：** {m.get('requested', 'unknown')}")
    L(f"**端点：** {c.get('base_url', 'unknown')}")
    note = m.get("note")
    if note:
        L(f"**备注：** {note}")
    L()

    # ── 1. 基本信息 ──
    L("---\n## 1. 基本信息\n")
    cc_status = b.get("chat_completions", "not_tested")
    if cc_status == "ok":
        L(f"- `/v1/chat/completions`: ✅ 正常")
        L(f"- API model 字段: `{m.get('returned', '?')}`")
        L(f"- 回复预览: \"{b.get('response_preview', '')}\"")
    else:
        L(f"- `/v1/chat/completions`: ❌ 失败 ({b.get('chat_error', 'unknown')})")

    resp_status = b.get("responses", "not_tested")
    if resp_status == "ok":
        L(f"- `/v1/responses`: ✅ 正常")
    elif resp_status == "fail":
        err = b.get("responses_error", "")
        L(f"- `/v1/responses`: ❌ 失败 ({err[:80]})")
    else:
        L(f"- `/v1/responses`: ⏭️ 未测试")

    mc = b.get("models_count")
    if mc is not None:
        L(f"- 可用模型: {mc} 个")

    usage = b.get("usage")
    if usage:
        L(f"- Usage: `{yaml.dump(usage, default_flow_style=True).strip()}`")
    L()

    # ── 2. 性能 ──
    L("---\n## 2. 性能 (探针响应时间)\n")
    rts = p.get("response_times_ms", [])
    if rts:
        L("| 探针 | 用时 |")
        L("|------|------|")
        # 从 probes 数据取探针名
        probes_data = data.get("probes", {}).get("results", [])
        for i, t in enumerate(rts):
            pid = probes_data[i].get("id", f"probe_{i+1}") if i < len(probes_data) else f"probe_{i+1}"
            L(f"| {pid} | {t:.0f}ms |")
        avg = p.get("response_times_avg_ms")
        if avg:
            L(f"| **平均** | **{avg:.0f}ms** |")
        L()
        throughput = p.get("throughput_tok_s")
        if throughput is not None:
            L(f"吞吐量: **{throughput:.1f} tok/s**")
        streaming = p.get("streaming_supported")
        if streaming is not None:
            L(f"流式支持: {'✅' if streaming else '❌'}")
    else:
        L("_未采集到性能数据_")
    L()

    # ── 3. 模型自称 ──
    L("---\n## 3. 模型身份自称\n")
    if s.get("samples"):
        L(fmt_self_id_table(s))
    else:
        L("_未测试_")
    L()

    # ── 4. 安全 ──
    L("---\n## 4. 安全 — 系统提示泄漏\n")
    L(fmt_security_table(sec))
    L()

    # ── 5. Agent Judge ──
    L("---\n## 5. Agent Judge 模型指纹检测\n")
    L(fmt_judgment(j))
    L()

    # ── 6. 能力探针 ──
    probes_data = data.get("probes", {}).get("results", [])
    if probes_data:
        # 正确性判断
        def probe_correct(p):
            exp = p.get("expected_answer")
            if exp is None:
                return None  # 无参考答案
            resp = p.get("response", "")
            if "ERROR" in resp:
                return False
            # 简单包含匹配
            ans = str(exp).strip()
            resp_clean = resp.replace(",", "").replace("$", "").replace(" ", "")
            ans_clean = ans.replace(",", "").replace("$", "").replace(" ", "")
            return ans_clean.lower() in resp_clean.lower() or ans.lower() in resp.lower()

        # 统计 Math + Logic 正确数
        scored = [p for p in probes_data if p.get("expected_answer") is not None and p.get("category") in ("math", "logic")]
        correct_count = sum(1 for p in scored if probe_correct(p))
        total_scored = len(scored)

        L("---\n## 6. 能力探针测试\n")
        if total_scored > 0:
            L(f"**数学/逻辑正确率: {correct_count}/{total_scored}**\n")
        L("| 探针 | 类别 | 正确 | 用时 | TTFT | tok/s | Token(入/出) |")
        L("|------|------|------|------|------|-------|-------------|")
        for p in probes_data:
            usage = p.get("usage", {})
            pt = usage.get("prompt_tokens", usage.get("input_tokens", "?"))
            ct = usage.get("completion_tokens", usage.get("output_tokens", "?"))
            tokens = f"{pt}/{ct}"
            ttft = p.get('ttft_ms', '')
            ttft_str = f"{ttft:.0f}ms" if isinstance(ttft, (int, float)) else ''
            tp = p.get('throughput_tok_s', '')
            tp_str = f"{tp:.1f}" if isinstance(tp, (int, float)) else ''
            # 正确性标记
            c = probe_correct(p)
            if c is None:
                correct_str = "-"
            elif c:
                correct_str = "✅"
            else:
                correct_str = "❌"
            L(f"| {p.get('id','')} | {p.get('category','')} | {correct_str} | {p.get('elapsed_ms',0):.0f}ms | {ttft_str} | {tp_str} | {tokens} |")
        L()
        L("### 详细回复\n")
        for p in probes_data:
            pid = p.get('id', '')
            prompt_text = (p.get('prompt') or '')[:200]
            response_text = p.get('response') or ''
            L(f"**{pid}** — _{p.get('category','')}_ — 问题: {prompt_text}")
            L()
            L("```")
            L(response_text[:2000])
            L("```")
            L()

    # ── 7. Token 注入检测 ──
    ti = data.get("token_injection", {})
    if ti.get("tested"):
        L("---\n## 7. Token 注入检测\n")
        injected = ti.get("injected_tokens")
        if injected and injected > 20:
            L(f"⚠️ **发现 ~{injected:.0f} 个隐藏注入 token/请求**")
            L(f"固定注入: {'是' if ti.get('injection_fixed') else '否（每次不同）'}")
            L()
            L("| 发送字符数 | 返回 input_tokens | 预期 | 差值 |")
            L("|-----------|-----------------|------|------|")
            L(f"| 1 | {ti.get('baseline_tokens','?')} | ~9 | ~{ti.get('baseline_tokens',0)-9} |")
        else:
            L("✅ 无明显 Token 注入")
            L(f"input_tokens 差值: {injected}")
        L()

    # ── 8. 隐藏 Prompt 提取 ──
    hp = data.get("hidden_prompt", {})
    if hp.get("tested"):
        L("---\n## 8. 隐藏 Prompt 提取\n")
        L("| 攻击方式 | 结果 | 长度 |")
        L("|---------|------|------|")
        for a in hp.get("attacks", []):
            s = "✅ 提取成功" if a.get("success") else "❌ 拒绝"
            L(f"| {a.get('id','')} | {s} | {a.get('length',0)} |")
        L()
        if hp.get("extracted_content"):
            L("### 还原的注入内容\n")
            L("```")
            L(hp["extracted_content"])
            L("```\n")
            if hp.get("cross_verified"):
                L("✅ 多方法交叉验证一致")
            else:
                L("⚠️ 仅一种方法成功，需人工验证")
        L()

    # ── 9. 架构识别 ──
    ra = data.get("relay_architecture", {})
    if ra.get("tested"):
        L("---\n## 9. 架构识别\n")
        if ra.get("is_one_api"):
            L("⚠️ **检测到 one-api / new-api 路由架构**（非官方直连）")
        else:
            L("架构类型: 未知")
        L()
        L(f"伪造模型请求错误: `{ra.get('fake_model_error','')[:200]}`")
        L()
        L("| 原生端点 | 状态 |")
        L("|---------|------|")
        for name, info in ra.get("native_endpoints", {}).items():
            status = "✅" if info.get("available") else f"❌ {info.get('status','?')}"
            L(f"| {name} | {status} |")
        L()

    L("---\n*报告由 collect_data.py 采集 + render_report.py 渲染*")
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="报告渲染")
    parser.add_argument("yaml_path", help="YAML 数据文件路径")
    parser.add_argument("--output", default=None, help="输出 Markdown 路径 (默认自动生成)")
    args = parser.parse_args()

    data = load_yaml(args.yaml_path)
    report = render(data)

    # 自动推断输出路径
    if not args.output:
        channel = data.get("channel", {}).get("name", "unknown")
        model = data.get("model", {}).get("requested", "unknown").replace("/", "-")
        args.output = f"reports/{channel}/{model}_report.md"

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"✅ 报告: {args.output}")


if __name__ == "__main__":
    main()
