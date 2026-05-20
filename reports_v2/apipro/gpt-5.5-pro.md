# 渠道质量测试报告：gpt-5.5-pro
**测试时间：** 2026-05-20 07:06
**模型：** gpt-5.5-pro
**端点：** https://api.apipro.ai/v1

---
## 1. 基本信息

- `/v1/chat/completions`: ❌ 失败 (Server error '500 Internal Server Error' for url 'https://api.apipro.ai/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500)
- `/v1/responses`: ⏭️ 未测试
- 可用模型: 197 个

---
## 2. 性能 (探针响应时间)

_未采集到性能数据_

---
## 3. 模型身份自称

_未测试_

---
## 4. 安全 — 系统提示泄漏

_未测试_

---
## 5. Agent Judge 模型指纹检测

📊 **能力范围: 无法评估（API 端点返回失败，无任何有效响应数据）**

### 吞吐量分析
无可用数据（吞吐量为 None tok/s，且非流式请求）

### 探针对照
无可用数据（chat/completions 端点返回 fail，无法执行探针测试）

### 模型自称分析
无可用数据（模型自称一致性为 None，无法分析）

### 安全与架构
系统提示泄漏探针 0 次，疑似泄漏 0 次；未检测到 one-api 路由架构特征；隐藏 prompt 检测结果未知

### Token 注入
无可用数据（未执行 Token 注入测试）

### 综合建议
> 该渠道端点（chat/completions）返回 fail，无法获取任何有效响应。吞吐量、探针表现、模型自称、Token 注入等关键维度均无数据。建议联系渠道方确认服务状态，或更换其他渠道进行测试。

---
*报告由 collect_data.py 采集 + render_report.py 渲染*