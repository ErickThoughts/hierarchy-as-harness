# results 目录说明

## 推荐阅读顺序

1. `summary_final.md`：最终总览和核心结论。
2. `summary_aligned.md`：realdata 对齐主实验的完整表。
3. `summary_score_modes.md`：PATH / 正文分开 dense scoring 的诊断。
4. `summary_improvement_experiments.md`：长度归一化与 routing 改进诊断。

## 正式结果 JSON

| 文件模式 | 含义 |
| --- | --- |
| `arxiv_predcomplete_aligned_dense_b{300,500,1000}.json` | 主结果：`full_text_main`。 |
| `arxiv_predcomplete_content_only_b{300,500,1000}.json` | 诊断：层级 dense scoring 只看正文。 |
| `arxiv_predcomplete_path_only_b{300,500,1000}.json` | 诊断：层级 dense scoring 只看 PATH。 |
| `arxiv_predcomplete_content_len220_b{300,500,1000}.json` | 改进诊断：正文-only + 约 220 字符窗口。 |
| `arxiv_predcomplete_content_routed_m{3,8}_b{300,500,1000}.json` | routing 诊断：先选 section 再检索。 |

## 非正式烟测文件

`smoke_*` 文件只用于开发过程中的小样本检查，不作为论文/报告结果引用。
