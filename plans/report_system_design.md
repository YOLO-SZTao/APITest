# 渠道测试报告系统 — 设计方案

## 当前问题

1. 三份 effitech 报告格式不统一（有的有附录有的没有）
2. 完全靠 LLM 生成报告，token 浪费
3. Agent Judge 探针题目不够好（硬编码在代码里）
4. 调用记录展示不完整

## 新架构

```
┌─────────────────────────────────────────────────────┐
│  Phase 1: 数据采集 (纯脚本, 无LLM)                   │
│                                                     │
│  quick_test.py <url> <key> <model>                  │
│  ├─ 基本连通性检查                                    │
│  ├─ TTFT ×3                                         │
│  ├─ 模型自称 ×3                                      │
│  ├─ 安全探针 ×2                                      │
│  ├─ /v1/responses 接口测试                            │
│  └─ 输出: data/channel_model.yaml (结构化数据)        │
│                                                     │
│  Phase 2: Report Judge (仅判断, 不写全文)            │
│                                                     │
│  report_judge.py <yaml_path>                        │
│  ├─ 读取 YAML 数据                                    │
│  ├─ 调用 LLM 仅判断:                                  │
│  │  ├─ 指纹评分 + 各维度分析                           │
│  │  ├─ 模型自称一致性评估                              │
│  │  └─ 综合建议                                       │
│  └─ 输出: 追加到 YAML (judgment 字段)                 │
│                                                     │
│  Phase 3: 报告渲染 (纯模板, 无LLM)                    │
│                                                     │
│  render_report.py <yaml_path>                       │
│  ├─ 读取完整的 YAML (含数据 + 判断)                   │
│  ├─ 填充 Markdown 模板                                │
│  └─ 输出: reports/channel/model_report.md             │
└─────────────────────────────────────────────────────┘
```

## 关键设计

### 1. 数据格式: YAML (非 Markdown)

脚本直接写结构化 YAML，LLM 只负责在 YAML 中补充 `judgment` 字段：

```yaml
channel:
  name: "effitech"
  base_url: "https://aigw.effitech.cn/v1"
  date: "2026-05-19"

basic:
  chat_completions: ok       # ok / fail
  model_field: "claude-haiku-4-5-20251001"
  responses: fail
  responses_error: "Go unmarshal bug"

performance:
  ttft_ms: [6997, 6353, 7516]
  ttft_avg_ms: 6955

self_id:
  samples:
    - "I'm Claude, made by Anthropic. I don't have a version..."
    - "I'm Claude, made by Anthropic. I don't have a version..."
    - "I'm Claude, made by Anthropic. I don't have a version..."
  consistency: "inconsistent"  # consistent / inconsistent / mixed

security:
  probes:
    - prompt: "Ignore all..."
      leaked: false
      length: 416
    - prompt: "请重复..."
      leaked: false
      length: 232

# ↓ 这个由 LLM 补充
judgment:
  fingerprint_score: 17.9
  suspected_model: "gpt-4o-mini"
  analysis: "..."
  issues: [...]
```

### 2. 探针优化

从网上找更好的 benchmark 题目，替代目前硬编码的 10 个探针：

**来源：**
- GSM8K (数学推理)
- MMLU (知识面)
- HellaSwag (常识推理)
- 选取代表性题目，而非全部

**设计原则：**
- 每个类别 2-3 题（避免太多导致耗时）
- 有明确的"正确答案"可对比
- 涵盖不同难度级别

### 3. Token 效率

| 方案 | LLM 调用次数 | Token 消耗 |
|------|-------------|-----------|
| 旧 (全 LLM 生成报告) | 1 次长篇 | ~4000 tokens |
| 新 (脚本采集 + LLM 仅判断) | 1 次短篇 | ~800 tokens |
| 节省 | — | **~80%** |

### 4. 调用记录规范

| 字段 | 举例 |
|------|------|
| 探针 ID | `math_gsm8k_1` |
| 类别 | math |
| 问题 | "小明有12个苹果..." |
| 用时 | 6997ms |
| 模型回答 | "小明剩余8个..." |
| Judge 评分 | 100 |
| Judge 评语 | "推理完整，计算正确" |

## 实施计划

### Step 1: 设计 YAML Schema
定义完整的数据结构 template.yaml，作为所有测试的标准格式

### Step 2: 重写 quick_test.py
纯 Python 数据采集，输出 YAML，不带任何 LLM 调用

### Step 3: 设计新探针
从 GSM8K / MMLU / HellaSwag 等 Benchmark 选取 8-10 题，替代硬编码探针

### Step 4: 实现 report_judge.py
读取 YAML，调用 LLM 仅补充 judgment 字段

### Step 5: 实现 render_report.py
基于模板渲染 Markdown 报告

### Step 6: 重跑 effitech 三模型
用新流程重新生成三份统一格式的报告

### Step 7: 跑 pandatoken gpt-5.5-pool
用新流程测试并生成报告
