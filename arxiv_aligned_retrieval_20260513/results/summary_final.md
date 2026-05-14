# arXiv 检索实验最终总览

本文件是 `arxiv_aligned_retrieval_20260513` 的入口总结。所有实验均为 retrieval-only：不跑 ReAct agent、不做 compose、不用 LLM judge。

## 该看哪套结果

| 用途 | 文件 | 结论口径 |
| --- | --- | --- |
| 正式主结果 | `summary_aligned.md` | realdata 对齐口径：层级 `PATH + 正文` dense scoring，Flat 为 flat_react-style 多 query 检索。 |
| PATH/正文拆分诊断 | `summary_score_modes.md` | 分别输出 `full_text` / `content_only` / `path_only`，不做加权。 |
| 改进实验 | `summary_improvement_experiments.md` | 比较主结果、正文-only、长度归一化、routing。 |
| 单个设置详细表 | `summary_content_only.md` / `summary_path_only.md` / `summary_content_len220.md` / routed summaries | 每个 budget 下的总体指标和 per-type 全指标。 |

## 数据与任务

- 任务数：77。
- 任务文件名保留历史 `150` 命名，但当前有效任务是 77 条。
- 评估开始会校验每题 `gold_nodes` 都能在 arXiv 行节点中找到。

| task_type | n |
| --- | ---: |
| cross_section_conflict | 9 |
| multi_hop | 12 |
| niche_fact | 21 |
| scope_collection | 15 |
| self_correct | 20 |

## 主结果：realdata 对齐口径

| Budget | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Pred-Gold) | 最好 |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 300 | 0.116 | 0.132 | 0.113 | +0.019 | +0.016 | Pred |
| 500 | 0.171 | 0.200 | 0.246 | -0.045 | +0.029 | Flat |
| 1000 | 0.216 | 0.265 | 0.318 | -0.053 | +0.049 | Flat |

主结果说明：budget=300 时 Pred-hier 略高于 Flat；budget=500/1000 时 Flat-react 更强。Pred-hier 平均高于 Gold-hier，但题级差异集中在少数样本，不能解释成 gold tree 被系统性打败。

## 最有效的改进诊断：content_len220

| Budget | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Pred-Gold) | 最好 |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 300 | 0.115 | 0.141 | 0.113 | +0.028 | +0.026 | Pred |
| 500 | 0.181 | 0.226 | 0.246 | -0.019 | +0.045 | Flat |
| 1000 | 0.239 | 0.324 | 0.318 | +0.005 | +0.084 | Pred |

这个设置保留 leaf/path 层级候选，但把正文切成约 220 字符窗口后再检索。它说明：控制 chunk 长度和边界后，arXiv 上的层级信号能被恢复一部分；budget=1000 时 Pred-hier 略高于 Flat-react。

## 按题型主结论

### 主结果 full_text_main：Pred-hier vs Flat-react

| Budget | Pred-hier 优于 Flat-react | 打平 | Flat-react 优于 Pred-hier |
| ---: | --- | --- | --- |
| 300 | multi_hop, niche_fact | - | cross_section_conflict, scope_collection, self_correct |
| 500 | multi_hop | - | cross_section_conflict, niche_fact, scope_collection, self_correct |
| 1000 | - | niche_fact | cross_section_conflict, multi_hop, scope_collection, self_correct |

### 改进结果 content_len220：Pred-hier vs Flat-react

| Budget | Pred-hier 优于 Flat-react | 打平 | Flat-react 优于 Pred-hier |
| ---: | --- | --- | --- |
| 300 | multi_hop, niche_fact, scope_collection | - | cross_section_conflict, self_correct |
| 500 | multi_hop, self_correct | scope_collection | cross_section_conflict, niche_fact |
| 1000 | niche_fact, self_correct | - | cross_section_conflict, multi_hop, scope_collection |

## 最终判断

- arXiv 上层级结构有信号，但收益不稳定，强依赖检索单元的 chunk 长度和边界。
- PATH 不是唯一原因：`content_only` 下 Pred 仍常高于 Gold，说明结构切分本身会影响 dense retrieval。
- 目前不能声称 Gold tree 必然优于 Pred tree。更准确的表述是：gold 结构语义更可信，但未必天然产生最适合 dense retriever 的 chunk。
- 不建议把 routing 作为主实验：它提前过滤 section，召回损失大。
- 建议汇报主线：先给 `full_text_main` 对齐结果，再用 `content_only` 和 `content_len220` 解释 PATH/长度/边界的影响。

## 文件索引

- `summary_aligned.md`：正式主结果，含对齐审计、总体指标、per-type 全指标。
- `summary_score_modes.md`：PATH/正文分开 dense scoring 的三套结果。
- `summary_improvement_experiments.md`：主结果、正文-only、长度归一化、routing 的横向对比。
- `summary_content_len220.md`：当前最好的改进诊断单表。
- `arxiv_predcomplete_*_b{300,500,1000}.json`：逐题结果和 summary。
