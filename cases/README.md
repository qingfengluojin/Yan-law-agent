# 评测案例

`cases.jsonl` 目前为空，等待 D7 建立 20 条正式案例。`cases.example.jsonl` 只展示字段格式，使用合成测试数据，不是正式评测集。

## 案例字段

| 字段 | 说明 |
|---|---|
| `id` | 稳定编号，例如 `single-01` |
| `question` | 用户问题 |
| `type` | `single_hop` / `multi_hop` / `no_answer` / `recovery` |
| `gold_article_ids` | 期望命中的条文 ID，格式为 `法律全称#条号` |
| `expected_behavior` | 期望输出行为，例如“命中第 38 条”“拒答”“降级” |
| `notes` | 可选备注 |

## 正式案例数量

| 类型 | 数量 |
|---|---:|
| 单跳检索 | 8 |
| 多步检索 | 6 |
| 无答案问题 | 3 |
| 工具失败 / 恢复 | 3 |
| 合计 | 20 |

## 评测报告只报告原始计数

```text
Gold article hit: x/20
Citation existence: x/20
Verbatim match: x/20
Unsupported citations: n
```

不得用 20 条样本外推总体准确率。