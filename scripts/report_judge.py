#!/usr/bin/env python3
"""报告评判脚本 — LLM 仅补充 YAML 中的 judgment 字段

读取采集好的 YAML 数据，调用 LLM 进行分析，补充 judgment 字段。

用法:
  python3 scripts/report_judge.py <yaml_path> [--judge-url <url>] [--judge-key <key>] [--judge-model <model>]
  
示例:
  python3 scripts/report_judge.py data/pandatoken/gpt-5.5-pool.yaml --judge-key sk-xxx
"""
import yaml, json, os, sys
from pathlib import Path


def load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(data: dict, path: str):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"  ✅ 已更新: {path}")


async def judge(data: dict, judge_url: str, judge_key: str, judge_model: str) -> dict:
    """调用 LLM 分析数据，返回 judgment 字段"""
    import httpx

    # 构建 summary (结构化信息，非全文)
    b = data.get("basic", {})
    p = data.get("performance", {})
    s = data.get("self_id", {})
    sec = data.get("security", {})
    m = data.get("model", {})

    # 统计安全泄漏
    leaked_count = sum(1 for pr in sec.get("probes", []) if pr.get("leaked"))

    summary = f"""## API 渠道测试数据

渠道: {data.get('channel', {}).get('name', '?')}
端点: {data.get('channel', {}).get('base_url', '?')}
请求模型: {m.get('requested', '?')}
API 返回模型字段: {m.get('returned', '?')}

### 性能
吞吐量: {p.get('throughput_tok_s', '?')} tok/s
流式支持: {'是' if p.get('streaming_supported') else '否'}

### 模型自称
{chr(10).join(f'  {i+1}. {s[:100]}' for i, s in enumerate(s.get('samples', [])))}
一致性: {s.get('consistency', '?')}

### 安全
系统提示泄漏探针: {len(sec.get('probes', []))} 次
疑似泄漏: {leaked_count} 次

### 基础信息
chat/completions: {b.get('chat_completions', '?')}
/responses: {b.get('responses', '?')}
"""

    system_prompt = """你是一位 AI 模型身份验证专家。给定一个第三方 API 渠道的测试数据，请**仅基于测试数据**判断，不要根据模型名称做判断——新模型、非官方模型名不等于虚假，关键看实际表现。

请分析以下维度，**只对可量化的给出数据对比，不可量化的只做文字分析，不要打总分**：

### 1️⃣ 吞吐量分析（可量化）
- 对比实测 tok/s 与主流 benchmark 参考值
- 判断是否在合理范围内

### 2️⃣ 探针表现
- 能力探针的完成情况、正确性
- **不要评分，不要分析**，只需列出参考结果和实际返回

### 3️⃣ 模型自称分析（不可量化）
- 3 次自称是否一致
- 是否直接表明身份，还是回避问题

### 4️⃣ 安全与架构分析（不可量化）
- 系统提示泄漏检测结果
- 是否识别为 one-api 路由架构
- 隐藏 prompt 检测结果

### 5️⃣ Token 注入（可量化）
- 发现的隐藏注入 token 数

### 基准参考
- Claude Opus 4.7 (2026.4): ~39.8 tok/s
- Claude Opus 4 (2025.5): ~30.9 tok/s
- Claude Sonnet 4: ~44-47 tok/s
- Claude Haiku 4.5: ~40-80 tok/s

以 JSON 格式回复，包含字段：
- throughput_assessment: "吞吐量分析（可量化数据+对比）"
- probes_comparison: "探针参考结果 vs 实际返回对照表"
- self_id_analysis: "模型自称分析"
- architecture_note: "安全与架构分析"
- token_injection_note: "Token 注入分析（如有）"
- capability_level: "能力范围描述（如：中高端模型水平、轻量模型水平），不要指认具体模型名"
- recommendation: "推荐" / "不推荐" / "需进一步验证"
- analysis: "综合建议"
"""

    body = {
        "model": judge_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": summary},
        ],
        "max_tokens": 1024,
        "temperature": 0.1,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{judge_url.rstrip('/')}/chat/completions",
            json=body,
            headers={
                "Authorization": f"Bearer {judge_key}",
                "Content-Type": "application/json",
            },
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]

    # 解析 JSON
    json_str = content.strip()
    if "```json" in content:
        json_str = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        json_str = content.split("```")[1].split("```")[0].strip()

    try:
        parsed = json.loads(json_str)
        return {
            "throughput_assessment": str(parsed.get("throughput_assessment", "")),
            "probes_comparison": str(parsed.get("probes_comparison", "")),
            "self_id_analysis": str(parsed.get("self_id_analysis", "")),
            "architecture_note": str(parsed.get("architecture_note", "")),
            "token_injection_note": str(parsed.get("token_injection_note", "")),
            "capability_level": str(parsed.get("capability_level", "")),
            "recommendation": str(parsed.get("recommendation", "需进一步验证")),
            "analysis": str(parsed.get("analysis", "")),
        }
    except (json.JSONDecodeError, ValueError) as e:
        return {
            "capability_level": "无法判断",
            "recommendation": "需进一步验证",
            "analysis": f"Judge 解析失败: {e}\n\n原始回复:\n{content[:500]}",
            "throughput_assessment": "解析失败",
        }


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="报告评判")
    parser.add_argument("yaml_path", help="YAML 数据文件路径")
    parser.add_argument("--judge-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--judge-key", default=os.environ.get("DEEPSEEK_KEY", ""))
    parser.add_argument("--judge-model", default="deepseek-chat")
    args = parser.parse_args()

    if not args.judge_key:
        print("❌ 需要提供 --judge-key 或设置 DEEPSEEK_KEY 环境变量")
        sys.exit(1)

    data = load_yaml(args.yaml_path)
    print(f"📊 正在分析: {args.yaml_path}")
    print(f"   Judge: {args.judge_model} @ {args.judge_url}")

    judgment = await judge(data, args.judge_url, args.judge_key, args.judge_model)
    data["judgment"] = judgment
    save_yaml(data, args.yaml_path)

    print(f"\n📋 结果:")
    ta = judgment.get('throughput_assessment', '')
    if ta:
        print(f"   吞吐量: {ta[:100]}")
    cl = judgment.get('capability_level', '')
    if cl:
        print(f"   能力范围: {cl[:80]}")
    print(f"   建议: {judgment.get('recommendation', '')}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
