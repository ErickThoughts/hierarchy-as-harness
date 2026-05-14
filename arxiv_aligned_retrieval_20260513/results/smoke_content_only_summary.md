# arXiv Pred-Complete Retrieval Summary

Protocol: retrieval-only; hierarchical uses multi-level ToolSpace leaf/path chunks (`PATH:` + subtree evidence); flat uses flat_react-style multi-query fusion. No ReAct agent, compose, or LLM judge is run.

## 对齐审计

| 检查项 | arXiv 当前逻辑 | 与 realdata 的关系 | 结论 |
| --- | --- | --- | --- |
| 数据加载 | `bundles_from_paths` 读取 `gold_level` / `predicted_level` / flat levels | 复用同名 loader；关键文件与 `core/` diff clean | 对齐 |
| 层级候选 | `ToolSpace.leaf_path_search_pool(doc_id)` 物化多层 `PATH:` + subtree chunk | 使用 realdata toolspace 的 leaf/path evidence 表示 | 对齐到检索单元 |
| 层级检索 | 在整篇文档 leaf/path 池上用 `_build_retrieval_queries` + `_query_weight` 做 dense fusion | 跳过 ReAct 工具轨迹，保留检索表示与 query fusion | retrieval-only 对齐 |
| Flat 对照 | `_query_variants_for_flat_react` 多轮变体 + `gather_flat_candidates` | 与 `runner_bodyrich.run_flat_react_episode` 的检索段一致 | 对齐 |
| Budget 填充 | `evaluate_at_budget` 字符预算、可截断最后一块 | 与 realdata budget 逻辑一致 | 对齐 |
| 指标 | `compute_budget_retrieval_metrics` + `retrieval_metrics` | 与 realdata 检索指标同源 | 对齐 |
| Agent/LLM | `llm_compose=False`，不调用 compose/judge/agent scoring | 用户要求只做检索 | 已移除 |

说明：这里的 Gold-hier 是 gold tree 生成的检索候选结构，不是 oracle 路由；它不会直接知道答案位置。

## 核心结论

- budget=300: 主指标 Coverage@budget_lenient 最好的是 Gold-hier (0.250)；Pred-Flat=-0.250，Pred-Gold=-0.250；题级 Pred>Gold / Gold>Pred / Tie = 0/1/1。
- Flat-react 在这些 budget 下整体强于 Pred-hier：Flat 更好的 budget=300；打平 budget=-。
- Gold-hier 平均不低于 Pred-hier：Gold 更好的 budget=300；打平 budget=-。

按题型看主指标 Coverage@budget_lenient 的 Pred-Flat：

| Budget | Pred-hier 优于 Flat-react | 打平 | Flat-react 优于 Pred-hier |
| ---: | --- | --- | --- |
| 300 | - | scope_collection | cross_section_conflict |

## 指标说明

| Metric | 含义 |
| --- | --- |
| Coverage@budget_lenient | 预算内 evidence 覆盖 gold line 的比例；主召回指标。 |
| MRR@chunks | 第一个命中 gold line 的 evidence chunk 的倒数排名。 |
| ChunkHit@1 | 排名第一的 evidence chunk 是否命中任一 gold line。 |
| Precision@k line | 预算内去重 retrieved line 的前 k 个中 gold line 占比。 |
| MRR line | 第一个 gold line 在 retrieved line 序列中的倒数排名。 |
| Hit@5 line | 前 5 个 retrieved line 是否命中任一 gold line。 |
| NDCG@10 line | 前 10 个 retrieved line 的排序质量。 |
| Coverage line | 预算内 retrieved line 对 gold line 的覆盖率；本协议下与 Coverage@budget_lenient 同源。 |
| Evidence chars | 实际写入 evidence 的字符数，受 budget 限制。 |
| Chunks kept | 预算内保留的 evidence chunk 数。 |

## 任务分布

| task_type | n |
| --- | ---: |
| cross_section_conflict | 1 |
| scope_collection | 1 |

## budget=300 (n=2)

Hierarchical dense scoring mode: `content_only`.
Hierarchical retrieval mode: `multi_level_leaf_path_pool`.

Candidate pool path-depth check:
- Gold-hier: n=398, path_depth_mean=1.427, max=3, hist={'1': 280, '2': 66, '3': 52}
- Pred-hier: n=344, path_depth_mean=1.459, max=3, hist={'1': 208, '2': 114, '3': 22}
- Flat-react: flat window chunks, n=58, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.250 | 0.000 | 0.250 | -0.250 | +0.000 | -0.250 |
| MRR@chunks | 0.500 | 0.000 | 0.500 | -0.500 | +0.000 | -0.500 |
| ChunkHit@1 | 0.500 | 0.000 | 0.500 | -0.500 | +0.000 | -0.500 |
| Precision@1 line | 0.500 | 0.000 | 0.500 | -0.500 | +0.000 | -0.500 |
| Precision@3 line | 0.250 | 0.000 | 0.167 | -0.167 | +0.083 | -0.250 |
| Precision@5 line | 0.250 | 0.000 | 0.100 | -0.100 | +0.150 | -0.250 |
| MRR line | 0.500 | 0.000 | 0.500 | -0.500 | +0.000 | -0.500 |
| Hit@5 line | 0.500 | 0.000 | 0.500 | -0.500 | +0.000 | -0.500 |
| NDCG@10 line | 0.250 | 0.000 | 0.250 | -0.250 | +0.000 | -0.250 |
| Coverage line | 0.250 | 0.000 | 0.250 | -0.250 | +0.000 | -0.250 |
| Evidence chars | 300.000 | 300.000 | 296.500 | +3.500 | +3.500 | +0.000 |
| Chunks kept | 1.500 | 1.000 | 1.000 | +0.000 | +0.500 | -0.500 |

### Per-type all metrics (budget=300)

| task_type | Metric | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | Coverage@budget_lenient | 1 | 0.500 | 0.000 | 0.500 | -0.500 | +0.000 | -0.500 |
| cross_section_conflict | MRR@chunks | 1 | 1.000 | 0.000 | 1.000 | -1.000 | +0.000 | -1.000 |
| cross_section_conflict | ChunkHit@1 | 1 | 1.000 | 0.000 | 1.000 | -1.000 | +0.000 | -1.000 |
| cross_section_conflict | Precision@1 line | 1 | 1.000 | 0.000 | 1.000 | -1.000 | +0.000 | -1.000 |
| cross_section_conflict | Precision@3 line | 1 | 0.500 | 0.000 | 0.333 | -0.333 | +0.167 | -0.500 |
| cross_section_conflict | Precision@5 line | 1 | 0.500 | 0.000 | 0.200 | -0.200 | +0.300 | -0.500 |
| cross_section_conflict | MRR line | 1 | 1.000 | 0.000 | 1.000 | -1.000 | +0.000 | -1.000 |
| cross_section_conflict | Hit@5 line | 1 | 1.000 | 0.000 | 1.000 | -1.000 | +0.000 | -1.000 |
| cross_section_conflict | NDCG@10 line | 1 | 0.500 | 0.000 | 0.500 | -0.500 | +0.000 | -0.500 |
| cross_section_conflict | Coverage line | 1 | 0.500 | 0.000 | 0.500 | -0.500 | +0.000 | -0.500 |
| cross_section_conflict | Evidence chars | 1 | 300.000 | 300.000 | 293.000 | +7.000 | +7.000 | +0.000 |
| cross_section_conflict | Chunks kept | 1 | 2.000 | 1.000 | 1.000 | +0.000 | +1.000 | -1.000 |
| scope_collection | Coverage@budget_lenient | 1 | 0.000 | 0.000 | 0.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | MRR@chunks | 1 | 0.000 | 0.000 | 0.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | ChunkHit@1 | 1 | 0.000 | 0.000 | 0.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | Precision@1 line | 1 | 0.000 | 0.000 | 0.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | Precision@3 line | 1 | 0.000 | 0.000 | 0.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | Precision@5 line | 1 | 0.000 | 0.000 | 0.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | MRR line | 1 | 0.000 | 0.000 | 0.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | Hit@5 line | 1 | 0.000 | 0.000 | 0.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | NDCG@10 line | 1 | 0.000 | 0.000 | 0.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | Coverage line | 1 | 0.000 | 0.000 | 0.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | Evidence chars | 1 | 300.000 | 300.000 | 300.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | Chunks kept | 1 | 1.000 | 1.000 | 1.000 | +0.000 | +0.000 | +0.000 |

