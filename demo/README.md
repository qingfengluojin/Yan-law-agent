# 劳动法条检索与引用核验 Agent 演示文档

> 本项目为技术演示，仅提供法条检索与引用核验，不构成法律意见。法条数据以官方来源为准，请在使用前核对最新版本。

本文件用于替代演示视频；按“3 分钟讲解脚本”逐段执行即可完成现场演示。

## 1. 演示目标

用 3–5 分钟展示以下闭环：

```text
用户提问
 → 检索相关法条
 → 获取条文原文
 → 核验引用
 → 输出带出处的回答
 → 证据不足时安全降级
```

演示重点不是“模型会不会聊天”，而是：

- 模型会不会选工具；
- 工具失败后能不能恢复；
- 引用是不是来自本轮工具结果；
- 引用能不能通过逐字核验；
- 没有依据时会不会停止输出结论。

---

## 2. 演示前检查

进入项目目录：

```powershell
cd C:\Users\29824\Desktop\Project\law\law-agent
$env:PYTHONPATH = "src"
```

检查测试：

```powershell
uv run pytest -q
```

预期：

```text
55 passed
```

检查数据：

```powershell
(Get-Content data\articles.jsonl -Encoding UTF8).Count
```

预期：

```text
40
```

检查报告：

```powershell
Get-ChildItem reports -File | Select-Object Name,Length
```

应该能看到：

```text
mock-report.md
mock-holdout-report.md
report.md
README.md
```

检查样例轨迹：

```powershell
Get-ChildItem traces\samples -File | Select-Object Name,Length
```

应该能看到 4 个 JSONL 文件。

---

## 3. 快速演示：Mock 模式

Mock 模式不需要 API Key，适合先确认程序能跑通。

### 命令

```powershell
uv run lawagent --agent --provider mock --data data/articles.jsonl "经济补偿按什么标准计算？"
```

### 预期

- 状态：通过核验；
- 引用《劳动合同法》第 47 条或实施条例第 27 条；
- 显示免责声明；
- 不调用外部模型。

### 适合讲解

> MockProvider 是确定性流程测试，不代表真实模型能力。  
> 它的作用是保证演示不依赖网络，并且每次运行结果稳定。

---

## 4. 真实模型演示：DeepSeek

### 4.1 设置环境变量

```powershell
$env:OPENAI_API_KEY = "你的 DeepSeek API Key"
$env:OPENAI_BASE_URL = "https://api.deepseek.com"
$env:LAWAGENT_MODEL = "deepseek-chat"
$env:PYTHONPATH = "src"
```

检查：

```powershell
if ($env:OPENAI_API_KEY) { "API key is set" } else { "API key is missing" }
$env:OPENAI_BASE_URL
$env:LAWAGENT_MODEL
```

预期：

```text
API key is set
https://api.deepseek.com
deepseek-chat
```

### 4.2 清屏

设置完环境变量后执行：

```powershell
Clear-Host
```

这样演示时不会把 Key 显示在屏幕上。

---

## 5. 演示场景一：单跳检索

### 问题

> 经济补偿按什么标准计算？

### 命令

```powershell
uv run lawagent --agent --provider openai --data data/articles.jsonl --show-trace "经济补偿按什么标准计算？"
```

### 预期结果

- 状态：通过核验；
- 检索到第 47 条；
- 可能同时引用实施条例第 27 条；
- 工具调用约 2 次；
- 轨迹中能看到 `search_statutes` 和 `verify_citation`。

### 讲解点

- 第 47 条规定经济补偿的计算标准；
- 第 27 条进一步规定月工资口径；
- 最终引用必须来自工具结果；
- 输出中的来源链接来自官方数据。

---

## 6. 演示场景二：多步检索与失败恢复

### 问题

> 公司不交社保，解除劳动合同能要补偿吗？

### 命令

```powershell
uv run lawagent --agent --provider openai --data data/articles.jsonl --show-trace "公司不交社保，解除劳动合同能要补偿吗？"
```

### 预期结果

- 状态：通过核验；
- 引用《劳动合同法》第 38 条；
- 引用《劳动合同法》第 46 条；
- 可能还引用第 47 条；
- 缺失事实中提示工作年限、月工资等。

### 重点展示

真实运行中可能出现：

```text
unknown_tool
→ search_statutes
→ verify_citation
→ final
```

这说明：

- 模型第一次调用工具时可能格式不正确；
- Agent 没有直接崩溃；
- 它根据错误提示重新选择了正确工具；
- 最终仍然完成了引用核验。

如果现场运行没有触发失败，可以打开已保存的轨迹：

```powershell
Get-Content traces\samples\deepseek-multi.jsonl -Encoding UTF8
```

展示其中的 `unknown_tool` 和后续恢复步骤。

---

## 7. 演示场景三：无答案问题

### 问题

> 公司未提供免费午餐，能否解除劳动合同？

### 命令

```powershell
uv run lawagent --agent --provider openai --data data/articles.jsonl --show-trace "公司未提供免费午餐，能否解除劳动合同？"
```

### 预期结果

- 不直接回答“能”或“不能”；
- 说明现有条文不足以直接得出结论；
- 可能引用第 38 条“劳动条件”；
- 列出缺失事实，例如：
  - 劳动合同或规章制度是否约定提供免费午餐；
  - 未提供午餐的具体情形；
  - 是否达到“未按约定提供劳动条件”的程度。

### 讲解点

> 这个项目宁愿说“证据不足”，也不愿意为了给出答案而编造法条。

---

## 8. 演示场景四：评测结果

### 命令

```powershell
Get-Content reports\mock-report.md -Encoding UTF8 -TotalCount 30
```

### 讲解结果

```text
Gold case hit: 17/17
Gold article recall: 28/28
Raw citation existence: 17/17
Raw unsupported citations: 0
Post-guard unsupported citations: 0
No-answer safe: 3/3
Recovery case hit: 3/3
Failure then success: 0/3
```

解释：

- `17/17`：17 条有 gold 的案例都命中了目标条文；
- `28/28`：所有 gold 条文都被工具检索覆盖；
- `17/17`：Mock 输出的原始引用都通过存在性核验；
- `0`：原始引用和最终引用都没有无依据项；
- `3/3`：3 个无答案问题都安全拒答；
- `0/3`：Mock 是固定流程演示，不模拟真实模型的失败恢复行为。

### 重要说明

> 这是 20 条人工案例的小规模回归，不能外推总体准确率。  
> baseline 是 retrieval-only，不是端到端 LLM baseline。

---

## 9. 查看 JSON 输出

如果想把结果交给程序处理：

```powershell
uv run lawagent --agent --provider openai --data data/articles.jsonl --json "经济补偿按什么标准计算？"
```

输出包含：

- `answer.summary`；
- `answer.citations`；
- `answer.missing_facts`；
- `answer.disclaimer`；
- `trace`；
- `steps`；
- `tool_calls`。

---

## 10. 保存轨迹

```powershell
uv run lawagent --agent --provider openai --data data/articles.jsonl --trace-out traces/my-demo.jsonl --run-out traces/my-demo-run.json "公司不交社保，解除劳动合同能要补偿吗？"
```

`--trace-out` 记录工具事件：

- 步骤编号；
- 决策摘要；
- 工具名称；
- 工具参数；
- 成功/失败；
- 错误原因和提示；
- 检索到的条文 ID；
- 工具耗时。

`--run-out` 额外记录最终答案、模型原始摘要、模型原始缺失事实、原始引用、最终引用、provider、model、数据 SHA256 和 Git commit。两者都不记录完整思维链。

---

## 11. 如果现场网络失败

按以下顺序降级：

### 方案 A：使用 Mock

```powershell
uv run lawagent --agent --provider mock --data data/articles.jsonl "经济补偿按什么标准计算？"
```

### 方案 B：展示已保存的真实轨迹

```powershell
Get-Content traces\samples\deepseek-multi.jsonl -Encoding UTF8
```

### 方案 C：展示评测报告

```powershell
Get-Content reports\mock-report.md -Encoding UTF8 -TotalCount 30
```

---

## 12. 项目边界

这个项目不做：

- 法律意见；
- 案件胜败判断；
- 赔偿金额预测；
- 起诉状、合同、律师函起草；
- 全量法律数据库；
- 地方规定和司法解释；
- 前端和多 Agent 编排。

---

## 13. 一句话总结

> 这个项目不是让模型“记住法条”，而是让模型在查法条时不能乱编，每一步都能被检查和复现。
