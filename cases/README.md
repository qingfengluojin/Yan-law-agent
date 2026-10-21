# 评测案例

## 数据集划分

- `retrieval_dev.jsonl`：10 条开发/回归问题，与 `cases.jsonl` 有 6 条重复，只用于检索调试。
- `cases.jsonl`：20 条正式回归案例，包含单跳、多跳、无答案和恢复路径。
- `holdout.jsonl`：10 条独立 holdout 案例，问题不与开发集或正式回归集重复，应作为最终泛化报告。

`cases.jsonl` 类型分布：

| 类型 | 数量 |
|---|---:|
| 单跳检索 | 8 |
| 多步检索 | 6 |
| 无答案问题 | 3 |
| 工具失败 / 恢复 | 3 |
| 合计 | 20 |

## 案例字段

| 字段 | 说明 |
|---|---|
| `id` | 稳定编号，例如 `single-01` |
| `question` | 用户问题 |
| `type` | `single_hop` / `multi_hop` / `no_answer` / `recovery` |
| `gold_article_ids` | 期望命中的条文 ID，格式为 `法律全称#条号` |
| `expected_behavior` | 期望输出行为，例如“命中第 38 条”“拒答”“降级” |
| `notes` | 可选备注 |

## 指标口径

报告必须同时区分：

```text
Raw model citations
Post-guard citations
Unique final citations
Duplicate final citations
Raw unsupported citations
Post-guard unsupported citations
```

开发集结果、Mock 结果和小样本 holdout 结果都不能外推总体准确率。
