# 评测报告说明

## 复核前真实评测（待在新数据快照上重跑）

- `report.deepseek-holdout.md`：使用 `deepseek-chat` 在 10 条独立 holdout 案例上的真实报告。
  - Gold case hit：9/9
  - Gold article recall：11/11
  - No-answer safe：1/1
  - Raw/Post-guard unsupported citations：0/0
- `report.deepseek-regression.md`：使用 `deepseek-chat` 在 20 条回归案例上的真实报告。
  - Gold case hit：17/17
  - Gold article recall：28/28
  - No-answer safe：3/3
  - Failure then success：1/3
  - Raw/Post-guard unsupported citations：0/0

两份报告原本对应源码提交 `31bb0b0`，但独立复核后数据日期、复核状态和 SHA256 已变化，因此这些结果只用于追溯，必须重新生成后才能作为最终报告。

## 离线报告

- `mock-report.md`：当前代码的 Mock 回归报告。
- `mock-holdout-report.md`：独立 holdout 集的 Mock 结果，用于离线流程验证。

## 历史报告

`report.md` 是 2026-10-21 早期的 DeepSeek 报告，生成于 raw/post-guard 指标拆分和引用去重之前，只保留用于追溯，不应直接当作当前代码结果。

## 重新生成

```powershell
uv run python scripts/evaluate.py --mode both --provider openai --data data/articles.jsonl --cases cases/holdout.jsonl --out reports/report.deepseek-holdout.md
uv run python scripts/evaluate.py --mode both --provider openai --data data/articles.jsonl --cases cases/cases.jsonl --out reports/report.deepseek-regression.md
```
