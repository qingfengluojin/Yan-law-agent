# 劳动法条检索与引用核验 Agent

> 本项目为技术演示，仅提供法条检索与引用核验，不构成法律意见。法条数据以官方来源为准，请在使用前核对最新版本。

一个刻意做小的劳动法 Agent 作品集项目：用 **3 个工具、一个受限 ReAct 循环和强制引用核验**，展示“检索 → 获取原文 → 核验引用 → 输出或安全降级”的完整闭环。

## 当前状态

- 项目骨架与核心代码已创建；
- `data/articles.jsonl` 已包含 40 条经核验条文，快照日期为 2026-10-20；
- 法律 34 条，行政法规 6 条，覆盖 5 个主题，每主题 8 条；
- `tests/fixtures/articles.jsonl` 是合成测试数据，不是正式法条；
- 默认 provider 为 `mock`，无需 API Key 即可复现完整流程。

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
 ├── Citation Verifier（存在性 + 连续片段核验）
 ├── Trace Recorder
 └── Output Guard（重新核验最终引用 + 降级）
 │
 ▼
data/articles.jsonl
```

## 快速开始

要求 Python 3.11+。

```powershell
# 方式一：安装为可编辑包
python -m pip install -e .

# 方式二：不安装，直接指定 src
$env:PYTHONPATH = "src"
```

使用正式数据跑通 Agent：

```powershell
python -m lawagent --agent --provider mock --data data/articles.jsonl "公司不交社保，解除劳动合同能要补偿吗？"
```
 
运行 baseline：

```powershell
python -m lawagent --baseline --data data/articles.jsonl "经济补偿按什么标准计算？"
```

输出 JSON 和轨迹：

```powershell
python -m lawagent --agent --provider mock --data data/articles.jsonl --json --trace-out traces/demo.jsonl "公司不交社保，解除劳动合同能要补偿吗？"
```

## 数据录入

正式数据文件为 `data/articles.jsonl`，每行一条：

```json
{
  "law": "中华人民共和国劳动合同法",
  "law_type": "法律",
  "article_no": "38",
  "text": "官方核验后的完整原文",
  "topic": "劳动合同解除",
  "source_url": "https://flk.npc.gov.cn/...",
  "verified_at": "2026-10-20",
  "status": "current"
}
```

录入前请先阅读 `data/SOURCES.md`。**未完成官方核验前，不要用空数据或测试数据生成法律结论。**

## 引用规则

1. 引用必须来自本轮工具结果；
2. 引用条文必须存在于数据集中；
3. 引用文本必须是原文的**连续片段**；
4. 禁止使用省略号、概括、改写或拼接；
5. 最终输出由代码再次核验全部 citations，不信任模型“已核验”的声明；
6. 没有通过核验的引用时，不输出法律结论。

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

不依赖 pytest 也可以运行：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

安装开发依赖后也可以使用：

```powershell
python -m pip install -e ".[dev]"
pytest
ruff check .
```
## 评测

```powershell
python scripts\evaluate.py --mode both --provider mock --data data/articles.jsonl --cases cases/cases.jsonl --out reports/report.md
```
## 已知局限

- 20 条评测案例已建立，但评测脚本和报告尚未完成；
- 真实 LLM 轨迹和演示视频尚未完成；
- baseline 当前是“单次检索 + 原文列表”，不是端到端 LLM 对照；
- 引用核验只能保证“文本存在且连续”，不能保证“该条文适用于具体案件”；
- MockProvider 只用于流程演示，不代表真实模型能力。
- 数据范围仅包括法律，以及《工伤保险条例》《劳动合同法实施条例》两部核心行政法规；不包含司法解释、地方规定和其他行政法规。

## 仓库结构

```text
law-agent/
├── README.md
├── DESIGN.md
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
│   ├── cases.jsonl
│   └── README.md
├── traces/samples/
├── tests/
│   ├── fixtures/articles.jsonl
│   └── test_*.py
└── demo/
```

## 开发顺序

D1 数据核验 → D2 检索 → D3 工具 → D4 Agent 循环 → D5 引用核验与降级 → D6 轨迹与 CLI → D7 评测 → D8 测试与 README → D9 演示视频 → D10 整理提交。