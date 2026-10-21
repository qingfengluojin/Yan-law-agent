# 劳动法条检索与引用核验 Agent

> 本项目为技术演示，仅提供法条检索与引用核验，不构成法律意见。法条数据以官方来源为准，请在使用前核对最新版本。

一个刻意做小的劳动法 Agent 作品集项目：用 **3 个工具、一个受限 ReAct 循环和强制引用核验**，展示“检索 → 获取原文 → 核验引用 → 输出或安全降级”的完整闭环。

## 当前状态

- 核心功能、40 条法条、20 条回归案例、10 条独立 holdout 案例和演示文档已完成；
- `data/articles.jsonl` 包含 40 条独立复核条文，快照日期为 2026-10-21；
- 当前数据的 `review_status` 均为 `independently_verified`，复核人为 `清风`；
- 法律 34 条，行政法规 6 条，覆盖 5 个主题，每主题 8 条；
- `tests/fixtures/articles.jsonl` 是合成测试数据，不是正式法条；
- 默认 provider 为 `mock`，默认输出模式为 `extractive`，无需 API Key 即可复现安全流程。

## 3 分钟了解项目

- **解决什么问题**：模型可能编造法条；本项目要求法条来自本地语料，并逐字核验引用。
- **核心做法**：模型选择 3 个工具，代码负责最终引用守卫、引用去重和安全降级。
- **默认策略**：`extractive` 模式只展示已核验原文，不把模型自由生成的结论混入最终答案。
- **可选策略**：`advisory` 模式允许模型生成辅助说明，但会明确标记为需要人工复核。
- **现场演示**：见 [`demo/README.md`](demo/README.md)；本项目不提供视频。

## 它做什么

1. 根据问题检索相关法条；
2. 获取指定条文完整原文；
3. 核验引用是否存在、是否为原文连续片段；
4. 引用不足时拒答或降级，只展示已获取的原文。

## 它不做什么

- 不判断案件胜负，不提供正式法律意见；
- 不做起诉状、合同、律师函起草；
- 不做多 Agent 编排、前端、数据库或向量检索；
- 不把模型记忆中的法条当作引用。

## 架构

```text
CLI
 │
 ▼
Agent Orchestrator
 ├── LLM Provider（Mock / OpenAI-compatible）
 ├── Tool Registry
 │    ├── search_statutes
 │    ├── get_article
 │    └── verify_citation
 ├── Retriever（BM25 + 条号路由 + 法律名称归一化）
 ├── Citation Verifier（存在性 + 连续片段核验 + 引用去重）
 ├── Output Guard（extractive / advisory + 降级）
 └── Run Manifest（数据哈希、Git commit、provider、model、时间）
 │
 ▼
data/articles.jsonl
```

## 快速开始

要求 Python 3.11+。

```powershell
uv sync
uv run pytest -q
```

使用正式数据跑通 Agent：

```powershell
uv run lawagent --agent --provider mock --data data/articles.jsonl "公司不交社保，解除劳动合同能要补偿吗？"
```

默认 `extractive` 模式只展示已核验原文。需要模型辅助说明时显式启用：

```powershell
uv run lawagent --agent --provider mock --output-mode advisory --data data/articles.jsonl "经济补偿按什么标准计算？"
```

运行 baseline：

```powershell
uv run lawagent --baseline --data data/articles.jsonl "经济补偿按什么标准计算？"
```

输出完整 JSON、事件轨迹和可复现运行记录：

```powershell
uv run lawagent --agent --provider mock --data data/articles.jsonl --json --trace-out traces/demo.jsonl --run-out traces/demo-run.json "公司不交社保，解除劳动合同能要补偿吗？"
```

`--trace-out` 保存工具事件；`--run-out` 额外保存最终答案、模型原始摘要与缺失事实、原始引用、通过守卫的引用、数据哈希、Git commit、Git dirty 状态、provider、model 和 prompt version。

Windows PowerShell 读取运行记录时请指定 UTF-8：`Get-Content -Raw -Encoding UTF8 traces/demo-run.json | ConvertFrom-Json`。

## 使用 DeepSeek

DeepSeek 通过 OpenAI-compatible 接口接入：

```powershell
uv sync --extra llm

$env:OPENAI_API_KEY = "你的 DeepSeek API Key"
$env:OPENAI_BASE_URL = "https://api.deepseek.com"
$env:LAWAGENT_MODEL = "deepseek-chat"

uv run lawagent --agent --provider openai --data data/articles.jsonl "经济补偿按什么标准计算？"
```

未设置 `OPENAI_API_KEY`、网络超时或模型调用失败时，CLI 会输出可读错误或安全终止，不会把异常伪装成法律结论。

## 评测结果

当前真实 DeepSeek 报告（基于 2026-10-21 独立复核数据）：

- `reports/report.deepseek-holdout.md`：10 条独立 holdout，Gold case hit `9/9`，Gold article recall `11/11`，No-answer safe `1/1`；
- `reports/report.deepseek-regression.md`：20 条回归，Gold case hit `17/17`，Gold article recall `28/28`，No-answer safe `3/3`。

`reports/mock-report.md` 是离线 Mock 回归报告，`reports/mock-holdout-report.md` 是离线 holdout 报告。所有报告同时区分：

- 模型原始输出引用；
- Output Guard 之后的引用；
- 原始无效引用；
- 最终无效引用；
- 去重后的唯一引用。

`reports/report.md` 是早期 DeepSeek 历史报告，生成于 raw/post-guard 指标拆分和引用去重之前，只保留用于追溯。当前真实结果以上述两份 DeepSeek 报告为准。

Baseline 是 top-8 检索结果，不是端到端 LLM 回答，因此 citation 指标不能直接与 Agent 比较。Gold hit 和 article recall 衡量工具检索覆盖，不等同于最终答案完整性。20 条回归样本和 10 条 holdout 样本都不能外推总体准确率。

## 样例轨迹

`traces/samples/` 包含 3 条主轨迹和 1 条无答案补充轨迹：

- `deepseek-simple.jsonl`：单跳检索 + 引用核验；
- `deepseek-multi.jsonl`：首次工具失败后重新选择工具并恢复；
- `deepseek-no-answer.jsonl`：证据不足时谨慎回答并列出缺失事实；
- `deepseek-no-answer-02.jsonl`：办公室噪音与工伤赔偿的无答案补充轨迹。

这些是历史工具事件轨迹，不包含完整最终答复。需要完整审计时，请使用新增的 `--run-out` 生成运行记录。

详细现场演示步骤见 [demo/README.md](demo/README.md)。

## 数据录入

正式数据文件为 `data/articles.jsonl`，每行一条：

```json
{
  "law": "中华人民共和国劳动合同法",
  "law_type": "法律",
  "article_no": "38",
  "text": "官方来源的完整原文",
  "topic": "劳动合同解除",
  "source_url": "https://flk.npc.gov.cn/...",
  "verified_at": "2026-10-21",
  "review_status": "independently_verified",
  "reviewer": "清风",
  "status": "current"
}
```

录入前请先阅读 `data/SOURCES.md`。`review_status=self_checked` 表示作者自检，不等同于独立复核。未完成官方核验前，不要用空数据或测试数据生成法律结论。

## 引用规则

1. 引用必须来自本轮工具结果；
2. 引用条文必须存在于数据集中；
3. 引用文本必须是原文的**连续片段**；
4. 禁止使用省略号、概括、改写或拼接；
5. 最终输出由代码再次核验全部 citations，并按条文和规范化文本去重；
6. 没有通过核验的引用时，不输出法律结论；
7. 默认 `extractive` 模式不输出自由法律结论；
8. `advisory` 模式中的模型说明始终标记为需要人工复核。

比较时只做 NFKC 和空白归一化，不改变标点和法律文本内容。

## 运行预算

| 项目 | 默认值 |
|---|---:|
| 最大步数 | 5 |
| 最大工具调用 | 4 |
| 连续失败终止 | 2 |
| 重复调用 | 直接拒绝 |

`max_tool_calls=4` 是为了覆盖一次完整的恢复路径：`search 失败 → 改写 search → get_article → verify_citation`。这是对计划书 v7.0 中“3 次”上限的有意修正。

## 测试

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

也可以使用标准库测试运行器：

```powershell
$env:PYTHONPATH = "src"
uv run python -m unittest discover -s tests -v
```

## 评测

```powershell
uv run python scripts/evaluate.py --mode both --provider mock --data data/articles.jsonl --cases cases/cases.jsonl --out reports/mock-report.md
uv run python scripts/evaluate.py --mode both --provider mock --data data/articles.jsonl --cases cases/holdout.jsonl --out reports/mock-holdout-report.md
uv run python scripts/evaluate.py --mode both --provider openai --data data/articles.jsonl --cases cases/holdout.jsonl --out reports/report.deepseek-chat.md
```

## 已知局限

- 20 条回归案例和 10 条 holdout 案例只能用于小型回归，不能外推总体准确率；
- Gold hit 是工具检索覆盖指标，不是最终答案完整性指标；
- baseline 是 retrieval-only，不是端到端 LLM baseline；
- 引用核验只能保证“文本存在且连续”，不能保证“该条文适用于具体案件”；
- 默认 `extractive` 模式牺牲了自然语言综合回答能力，换取更低的结论风险；
- `advisory` 模式仍是模型生成内容，必须人工复核；
- raw citation 指标仍不覆盖 JSON 解析阶段就被丢弃的非法 citation 结构；
- MockProvider 只用于流程演示，其无答案识别是固定演示场景路由，不代表通用 answerability 能力；
- 40 条法条已由独立复核人 `清风` 复核，核对范围为文本、条号、来源和现行状态；
- 数据范围仅包括法律，以及《工伤保险条例》《劳动合同法实施条例》两部核心行政法规；不包含司法解释、地方规定和其他行政法规。

## 隐私与许可

使用真实 provider 时，用户问题、工具轨迹摘要和相关法条文本会发送到配置的第三方 API。不要输入未经授权的个人敏感信息。

代码使用 MIT License，见 `LICENSE`。法条数据的来源和再分发边界见 `data/SOURCES.md`。

## 仓库结构

```text
law-agent/
├── README.md
├── DESIGN.md
├── LICENSE
├── pyproject.toml
├── src/lawagent/
│   ├── __init__.py
│   ├── __main__.py
│   ├── agent.py
│   ├── cli.py
│   ├── llm.py
│   ├── retriever.py
│   ├── schema.py
│   ├── tools.py
│   ├── trace.py
│   └── verify.py
├── data/
│   ├── articles.jsonl
│   └── SOURCES.md
├── cases/
│   ├── retrieval_dev.jsonl
│   ├── cases.jsonl
│   ├── holdout.jsonl
│   └── README.md
├── tests/
│   ├── fixtures/articles.jsonl
│   └── test_*.py
├── scripts/
│   ├── build_candidate_csv.py
│   ├── set_verified_at.py
│   ├── convert_articles.py
│   ├── retrieval_check.py
│   └── evaluate.py
├── reports/
│   ├── report.deepseek-holdout.md
│   ├── report.deepseek-regression.md
│   ├── mock-report.md
│   ├── mock-holdout-report.md
│   ├── report.md
│   └── README.md
├── traces/
│   └── samples/
│       ├── deepseek-simple.jsonl
│       ├── deepseek-multi.jsonl
│       ├── deepseek-no-answer.jsonl
│       └── deepseek-no-answer-02.jsonl
└── demo/
    └── README.md

```

## 开发顺序

D1 数据核验 → D2 检索 → D3 工具 → D4 Agent 循环 → D5 引用核验与降级 → D6 轨迹与 CLI → D7 评测 → D8 测试与 README → D9 演示文档 → D10 整理提交。
