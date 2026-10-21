# 样例轨迹

本目录保存真实 DeepSeek 运行的 JSONL 轨迹。

## deepseek-simple.jsonl

单跳问题：

- 检索经济补偿计算标准；
- 调用 `verify_citation`；
- 最终引用第 47 条和实施条例第 27 条。

## deepseek-multi.jsonl

多步问题：

- 第 1 步出现 `unknown_tool`；
- 第 2 步重新选择 `search_statutes`；
- 第 3 步调用 `verify_citation`；
- 第 4 步完成回答。

这条轨迹用于展示工具失败后的恢复能力。

## deepseek-no-answer.jsonl

无答案问题：

- 检索到相关条文；
- 回答明确说明“仅凭现有条文无法直接得出结论”；
- 列出缺失事实；
- 不强行给出法律结论。

## deepseek-no-answer-02.jsonl

无答案问题的补充轨迹：

- 讨论办公室噪音与工伤赔偿；
- 说明现有条文不足以支持结论；
- 列出医疗诊断、职业病诊断等缺失事实。
## 完整运行记录

已有样例只保存工具事件，适合展示工具选择，但不包含最终答案。需要审计最终输出时，使用 `--run-out` 保存完整 `RunResult` 和运行元数据。
