# 评测报告说明

- `report.md`：2026-10-21 的 DeepSeek 历史报告，保留用于追溯。该报告生成于 raw/post-guard 指标拆分和引用去重之前，不应直接当作当前代码的复现结果。
- `mock-report.md`：当前代码的 Mock 离线回归报告，覆盖 20 条人工案例。
- `mock-holdout-report.md`：独立 holdout 集的 Mock 结果，问题不与开发集或正式评测集重复。

仓库不保存 API Key，因此代码更新后没有自动重跑真实 DeepSeek 评测。需要重新验证时，请使用：

```powershell
uv run python scripts/evaluate.py --mode both --provider openai --data data/articles.jsonl --cases cases/cases.jsonl --out reports/report.deepseek-chat.md
```
