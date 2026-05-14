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

- budget=300: 主指标 Coverage@budget_lenient 最好的是 Flat-react (0.113)；Pred-Flat=-0.026，Pred-Gold=-0.006；题级 Pred>Gold / Gold>Pred / Tie = 1/2/74。
- budget=500: 主指标 Coverage@budget_lenient 最好的是 Flat-react (0.246)；Pred-Flat=-0.110，Pred-Gold=-0.013；题级 Pred>Gold / Gold>Pred / Tie = 2/3/72。
- budget=1000: 主指标 Coverage@budget_lenient 最好的是 Flat-react (0.318)；Pred-Flat=-0.111，Pred-Gold=+0.026；题级 Pred>Gold / Gold>Pred / Tie = 4/2/71。
- Flat-react 在这些 budget 下整体强于 Pred-hier：Flat 更好的 budget=300, 500, 1000；打平 budget=-。
- Pred-hier 与 Gold-hier 的差异随 budget 改变：Pred 更好的 budget=1000；Gold 更好的 budget=300, 500；打平 budget=-。

按题型看主指标 Coverage@budget_lenient 的 Pred-Flat：

| Budget | Pred-hier 优于 Flat-react | 打平 | Flat-react 优于 Pred-hier |
| ---: | --- | --- | --- |
| 300 | multi_hop | - | cross_section_conflict, niche_fact, scope_collection, self_correct |
| 500 | multi_hop | - | cross_section_conflict, niche_fact, scope_collection, self_correct |
| 1000 | - | - | cross_section_conflict, multi_hop, niche_fact, scope_collection, self_correct |

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
| cross_section_conflict | 9 |
| multi_hop | 12 |
| niche_fact | 21 |
| scope_collection | 15 |
| self_correct | 20 |

## budget=300 (n=77)

Hierarchical dense scoring mode: `content_only`.
Hierarchical retrieval mode: `routed_leaf_path`.
Route top sections: `3`.

Candidate pool path-depth check:
- Gold-hier: n=2779, path_depth_mean=2.184, max=5, hist={'1': 216, '2': 1841, '3': 719, '4': 1, '5': 2}
- Pred-hier: n=2329, path_depth_mean=1.851, max=5, hist={'1': 624, '2': 1436, '3': 263, '4': 4, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.093 | 0.087 | 0.113 | -0.026 | -0.019 | -0.006 |
| MRR@chunks | 0.147 | 0.134 | 0.195 | -0.061 | -0.048 | -0.013 |
| ChunkHit@1 | 0.143 | 0.130 | 0.195 | -0.065 | -0.052 | -0.013 |
| Precision@1 line | 0.143 | 0.117 | 0.065 | +0.052 | +0.078 | -0.026 |
| Precision@3 line | 0.128 | 0.115 | 0.043 | +0.071 | +0.084 | -0.013 |
| Precision@5 line | 0.128 | 0.115 | 0.045 | +0.070 | +0.083 | -0.013 |
| MRR line | 0.147 | 0.128 | 0.106 | +0.021 | +0.041 | -0.019 |
| Hit@5 line | 0.156 | 0.143 | 0.195 | -0.052 | -0.039 | -0.013 |
| NDCG@10 line | 0.094 | 0.088 | 0.092 | -0.004 | +0.002 | -0.006 |
| Coverage line | 0.093 | 0.087 | 0.113 | -0.026 | -0.019 | -0.006 |
| Evidence chars | 298.156 | 298.961 | 299.351 | -0.390 | -1.195 | +0.805 |
| Chunks kept | 1.468 | 1.429 | 1.039 | +0.390 | +0.429 | -0.039 |

### Per-type all metrics (budget=300)

| task_type | Metric | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | Coverage@budget_lenient | 9 | 0.139 | 0.028 | 0.176 | -0.148 | -0.037 | -0.111 |
| cross_section_conflict | MRR@chunks | 9 | 0.333 | 0.111 | 0.444 | -0.333 | -0.111 | -0.222 |
| cross_section_conflict | ChunkHit@1 | 9 | 0.333 | 0.111 | 0.444 | -0.333 | -0.111 | -0.222 |
| cross_section_conflict | Precision@1 line | 9 | 0.333 | 0.111 | 0.222 | -0.111 | +0.111 | -0.222 |
| cross_section_conflict | Precision@3 line | 9 | 0.278 | 0.111 | 0.111 | +0.000 | +0.167 | -0.167 |
| cross_section_conflict | Precision@5 line | 9 | 0.278 | 0.111 | 0.104 | +0.007 | +0.174 | -0.167 |
| cross_section_conflict | MRR line | 9 | 0.333 | 0.111 | 0.281 | -0.170 | +0.052 | -0.222 |
| cross_section_conflict | Hit@5 line | 9 | 0.333 | 0.111 | 0.444 | -0.333 | -0.111 | -0.222 |
| cross_section_conflict | NDCG@10 line | 9 | 0.147 | 0.035 | 0.144 | -0.109 | +0.002 | -0.111 |
| cross_section_conflict | Coverage line | 9 | 0.139 | 0.028 | 0.176 | -0.148 | -0.037 | -0.111 |
| cross_section_conflict | Evidence chars | 9 | 297.778 | 297.778 | 299.222 | -1.444 | -1.444 | +0.000 |
| cross_section_conflict | Chunks kept | 9 | 1.222 | 1.111 | 1.111 | +0.000 | +0.111 | -0.111 |
| multi_hop | Coverage@budget_lenient | 12 | 0.069 | 0.069 | 0.042 | +0.028 | +0.028 | +0.000 |
| multi_hop | MRR@chunks | 12 | 0.167 | 0.167 | 0.083 | +0.083 | +0.083 | +0.000 |
| multi_hop | ChunkHit@1 | 12 | 0.167 | 0.167 | 0.083 | +0.083 | +0.083 | +0.000 |
| multi_hop | Precision@1 line | 12 | 0.167 | 0.083 | 0.083 | +0.000 | +0.083 | -0.083 |
| multi_hop | Precision@3 line | 12 | 0.167 | 0.125 | 0.028 | +0.097 | +0.139 | -0.042 |
| multi_hop | Precision@5 line | 12 | 0.167 | 0.125 | 0.017 | +0.108 | +0.150 | -0.042 |
| multi_hop | MRR line | 12 | 0.167 | 0.125 | 0.083 | +0.042 | +0.083 | -0.042 |
| multi_hop | Hit@5 line | 12 | 0.167 | 0.167 | 0.083 | +0.083 | +0.083 | +0.000 |
| multi_hop | NDCG@10 line | 12 | 0.073 | 0.073 | 0.042 | +0.032 | +0.032 | +0.000 |
| multi_hop | Coverage line | 12 | 0.069 | 0.069 | 0.042 | +0.028 | +0.028 | +0.000 |
| multi_hop | Evidence chars | 12 | 300.000 | 300.000 | 300.000 | +0.000 | +0.000 | +0.000 |
| multi_hop | Chunks kept | 12 | 1.333 | 1.333 | 1.000 | +0.333 | +0.333 | +0.000 |
| niche_fact | Coverage@budget_lenient | 21 | 0.063 | 0.063 | 0.071 | -0.008 | -0.008 | +0.000 |
| niche_fact | MRR@chunks | 21 | 0.063 | 0.063 | 0.095 | -0.032 | -0.032 | +0.000 |
| niche_fact | ChunkHit@1 | 21 | 0.048 | 0.048 | 0.095 | -0.048 | -0.048 | +0.000 |
| niche_fact | Precision@1 line | 21 | 0.048 | 0.048 | 0.048 | +0.000 | +0.000 | +0.000 |
| niche_fact | Precision@3 line | 21 | 0.063 | 0.063 | 0.016 | +0.048 | +0.048 | +0.000 |
| niche_fact | Precision@5 line | 21 | 0.063 | 0.063 | 0.021 | +0.042 | +0.042 | +0.000 |
| niche_fact | MRR line | 21 | 0.063 | 0.063 | 0.060 | +0.004 | +0.004 | +0.000 |
| niche_fact | Hit@5 line | 21 | 0.095 | 0.095 | 0.095 | +0.000 | +0.000 | +0.000 |
| niche_fact | NDCG@10 line | 21 | 0.059 | 0.059 | 0.060 | -0.000 | -0.000 | +0.000 |
| niche_fact | Coverage line | 21 | 0.063 | 0.063 | 0.071 | -0.008 | -0.008 | +0.000 |
| niche_fact | Evidence chars | 21 | 297.905 | 297.905 | 299.000 | -1.095 | -1.095 | +0.000 |
| niche_fact | Chunks kept | 21 | 1.619 | 1.476 | 1.048 | +0.429 | +0.571 | -0.143 |
| scope_collection | Coverage@budget_lenient | 15 | 0.050 | 0.050 | 0.083 | -0.033 | -0.033 | +0.000 |
| scope_collection | MRR@chunks | 15 | 0.133 | 0.133 | 0.200 | -0.067 | -0.067 | +0.000 |
| scope_collection | ChunkHit@1 | 15 | 0.133 | 0.133 | 0.200 | -0.067 | -0.067 | +0.000 |
| scope_collection | Precision@1 line | 15 | 0.133 | 0.133 | 0.000 | +0.133 | +0.133 | +0.000 |
| scope_collection | Precision@3 line | 15 | 0.133 | 0.133 | 0.022 | +0.111 | +0.111 | +0.000 |
| scope_collection | Precision@5 line | 15 | 0.133 | 0.133 | 0.040 | +0.093 | +0.093 | +0.000 |
| scope_collection | MRR line | 15 | 0.133 | 0.133 | 0.056 | +0.078 | +0.078 | +0.000 |
| scope_collection | Hit@5 line | 15 | 0.133 | 0.133 | 0.200 | -0.067 | -0.067 | +0.000 |
| scope_collection | NDCG@10 line | 15 | 0.055 | 0.055 | 0.048 | +0.006 | +0.006 | +0.000 |
| scope_collection | Coverage line | 15 | 0.050 | 0.050 | 0.083 | -0.033 | -0.033 | +0.000 |
| scope_collection | Evidence chars | 15 | 300.000 | 300.000 | 298.733 | +1.267 | +1.267 | +0.000 |
| scope_collection | Chunks kept | 15 | 1.400 | 1.400 | 1.000 | +0.400 | +0.400 | +0.000 |
| self_correct | Coverage@budget_lenient | 20 | 0.150 | 0.175 | 0.192 | -0.017 | -0.042 | +0.025 |
| self_correct | MRR@chunks | 20 | 0.150 | 0.200 | 0.250 | -0.050 | -0.100 | +0.050 |
| self_correct | ChunkHit@1 | 20 | 0.150 | 0.200 | 0.250 | -0.050 | -0.100 | +0.050 |
| self_correct | Precision@1 line | 20 | 0.150 | 0.200 | 0.050 | +0.150 | +0.100 | +0.050 |
| self_correct | Precision@3 line | 20 | 0.100 | 0.150 | 0.067 | +0.083 | +0.033 | +0.050 |
| self_correct | Precision@5 line | 20 | 0.100 | 0.150 | 0.064 | +0.086 | +0.036 | +0.050 |
| self_correct | MRR line | 20 | 0.150 | 0.200 | 0.129 | +0.071 | +0.021 | +0.050 |
| self_correct | Hit@5 line | 20 | 0.150 | 0.200 | 0.250 | -0.050 | -0.100 | +0.050 |
| self_correct | NDCG@10 line | 20 | 0.150 | 0.175 | 0.166 | +0.009 | -0.016 | +0.025 |
| self_correct | Coverage line | 20 | 0.150 | 0.175 | 0.192 | -0.017 | -0.042 | +0.025 |
| self_correct | Evidence chars | 20 | 296.100 | 299.200 | 299.850 | -0.650 | -3.750 | +3.100 |
| self_correct | Chunks kept | 20 | 1.550 | 1.600 | 1.050 | +0.550 | +0.500 | +0.050 |

## budget=500 (n=77)

Hierarchical dense scoring mode: `content_only`.
Hierarchical retrieval mode: `routed_leaf_path`.
Route top sections: `3`.

Candidate pool path-depth check:
- Gold-hier: n=2779, path_depth_mean=2.184, max=5, hist={'1': 216, '2': 1841, '3': 719, '4': 1, '5': 2}
- Pred-hier: n=2329, path_depth_mean=1.851, max=5, hist={'1': 624, '2': 1436, '3': 263, '4': 4, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.148 | 0.135 | 0.246 | -0.110 | -0.097 | -0.013 |
| MRR@chunks | 0.199 | 0.180 | 0.325 | -0.145 | -0.126 | -0.019 |
| ChunkHit@1 | 0.182 | 0.156 | 0.312 | -0.156 | -0.130 | -0.026 |
| Precision@1 line | 0.143 | 0.117 | 0.065 | +0.052 | +0.078 | -0.026 |
| Precision@3 line | 0.132 | 0.121 | 0.063 | +0.058 | +0.069 | -0.011 |
| Precision@5 line | 0.132 | 0.121 | 0.070 | +0.051 | +0.062 | -0.011 |
| MRR line | 0.180 | 0.160 | 0.143 | +0.017 | +0.036 | -0.019 |
| Hit@5 line | 0.221 | 0.208 | 0.312 | -0.104 | -0.091 | -0.013 |
| NDCG@10 line | 0.150 | 0.137 | 0.159 | -0.021 | -0.008 | -0.013 |
| Coverage line | 0.148 | 0.135 | 0.246 | -0.110 | -0.097 | -0.013 |
| Evidence chars | 490.286 | 493.766 | 499.195 | -5.429 | -8.909 | +3.481 |
| Chunks kept | 1.909 | 1.896 | 1.273 | +0.623 | +0.636 | -0.013 |

### Per-type all metrics (budget=500)

| task_type | Metric | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | Coverage@budget_lenient | 9 | 0.139 | 0.028 | 0.176 | -0.148 | -0.037 | -0.111 |
| cross_section_conflict | MRR@chunks | 9 | 0.333 | 0.111 | 0.444 | -0.333 | -0.111 | -0.222 |
| cross_section_conflict | ChunkHit@1 | 9 | 0.333 | 0.111 | 0.444 | -0.333 | -0.111 | -0.222 |
| cross_section_conflict | Precision@1 line | 9 | 0.333 | 0.111 | 0.222 | -0.111 | +0.111 | -0.222 |
| cross_section_conflict | Precision@3 line | 9 | 0.222 | 0.111 | 0.111 | +0.000 | +0.111 | -0.111 |
| cross_section_conflict | Precision@5 line | 9 | 0.222 | 0.111 | 0.094 | +0.017 | +0.128 | -0.111 |
| cross_section_conflict | MRR line | 9 | 0.333 | 0.111 | 0.281 | -0.170 | +0.052 | -0.222 |
| cross_section_conflict | Hit@5 line | 9 | 0.333 | 0.111 | 0.444 | -0.333 | -0.111 | -0.222 |
| cross_section_conflict | NDCG@10 line | 9 | 0.147 | 0.035 | 0.144 | -0.109 | +0.002 | -0.111 |
| cross_section_conflict | Coverage line | 9 | 0.139 | 0.028 | 0.176 | -0.148 | -0.037 | -0.111 |
| cross_section_conflict | Evidence chars | 9 | 484.778 | 483.000 | 500.000 | -17.000 | -15.222 | -1.778 |
| cross_section_conflict | Chunks kept | 9 | 1.667 | 1.444 | 1.556 | -0.111 | +0.111 | -0.222 |
| multi_hop | Coverage@budget_lenient | 12 | 0.111 | 0.111 | 0.083 | +0.028 | +0.028 | +0.000 |
| multi_hop | MRR@chunks | 12 | 0.250 | 0.250 | 0.167 | +0.083 | +0.083 | +0.000 |
| multi_hop | ChunkHit@1 | 12 | 0.250 | 0.250 | 0.167 | +0.083 | +0.083 | +0.000 |
| multi_hop | Precision@1 line | 12 | 0.167 | 0.083 | 0.083 | +0.000 | +0.083 | -0.083 |
| multi_hop | Precision@3 line | 12 | 0.167 | 0.153 | 0.056 | +0.097 | +0.111 | -0.014 |
| multi_hop | Precision@5 line | 12 | 0.167 | 0.153 | 0.037 | +0.115 | +0.129 | -0.014 |
| multi_hop | MRR line | 12 | 0.208 | 0.167 | 0.111 | +0.056 | +0.097 | -0.042 |
| multi_hop | Hit@5 line | 12 | 0.250 | 0.250 | 0.167 | +0.083 | +0.083 | +0.000 |
| multi_hop | NDCG@10 line | 12 | 0.115 | 0.115 | 0.068 | +0.047 | +0.047 | +0.000 |
| multi_hop | Coverage line | 12 | 0.111 | 0.111 | 0.083 | +0.028 | +0.028 | +0.000 |
| multi_hop | Evidence chars | 12 | 500.000 | 500.000 | 498.250 | +1.750 | +1.750 | +0.000 |
| multi_hop | Chunks kept | 12 | 1.833 | 1.833 | 1.167 | +0.667 | +0.667 | +0.000 |
| niche_fact | Coverage@budget_lenient | 21 | 0.135 | 0.087 | 0.333 | -0.246 | -0.198 | -0.048 |
| niche_fact | MRR@chunks | 21 | 0.135 | 0.087 | 0.357 | -0.270 | -0.222 | -0.048 |
| niche_fact | ChunkHit@1 | 21 | 0.095 | 0.048 | 0.333 | -0.286 | -0.238 | -0.048 |
| niche_fact | Precision@1 line | 21 | 0.048 | 0.048 | 0.048 | +0.000 | +0.000 | +0.000 |
| niche_fact | Precision@3 line | 21 | 0.111 | 0.087 | 0.032 | +0.056 | +0.079 | -0.024 |
| niche_fact | Precision@5 line | 21 | 0.111 | 0.087 | 0.069 | +0.018 | +0.042 | -0.024 |
| niche_fact | MRR line | 21 | 0.111 | 0.087 | 0.123 | -0.036 | -0.012 | -0.024 |
| niche_fact | Hit@5 line | 21 | 0.190 | 0.143 | 0.333 | -0.190 | -0.143 | -0.048 |
| niche_fact | NDCG@10 line | 21 | 0.130 | 0.083 | 0.182 | -0.099 | -0.052 | -0.048 |
| niche_fact | Coverage line | 21 | 0.135 | 0.087 | 0.333 | -0.246 | -0.198 | -0.048 |
| niche_fact | Evidence chars | 21 | 487.095 | 487.095 | 500.000 | -12.905 | -12.905 | +0.000 |
| niche_fact | Chunks kept | 21 | 2.000 | 1.905 | 1.238 | +0.667 | +0.762 | -0.095 |
| scope_collection | Coverage@budget_lenient | 15 | 0.067 | 0.067 | 0.167 | -0.100 | -0.100 | +0.000 |
| scope_collection | MRR@chunks | 15 | 0.133 | 0.133 | 0.267 | -0.133 | -0.133 | +0.000 |
| scope_collection | ChunkHit@1 | 15 | 0.133 | 0.133 | 0.267 | -0.133 | -0.133 | +0.000 |
| scope_collection | Precision@1 line | 15 | 0.133 | 0.133 | 0.000 | +0.133 | +0.133 | +0.000 |
| scope_collection | Precision@3 line | 15 | 0.100 | 0.100 | 0.056 | +0.044 | +0.044 | +0.000 |
| scope_collection | Precision@5 line | 15 | 0.100 | 0.100 | 0.073 | +0.027 | +0.027 | +0.000 |
| scope_collection | MRR line | 15 | 0.133 | 0.133 | 0.089 | +0.044 | +0.044 | +0.000 |
| scope_collection | Hit@5 line | 15 | 0.133 | 0.133 | 0.267 | -0.133 | -0.133 | +0.000 |
| scope_collection | NDCG@10 line | 15 | 0.076 | 0.076 | 0.123 | -0.047 | -0.047 | +0.000 |
| scope_collection | Coverage line | 15 | 0.067 | 0.067 | 0.167 | -0.100 | -0.100 | +0.000 |
| scope_collection | Evidence chars | 15 | 498.000 | 499.467 | 498.133 | +1.333 | -0.133 | +1.467 |
| scope_collection | Chunks kept | 15 | 1.933 | 1.800 | 1.267 | +0.533 | +0.667 | -0.133 |
| self_correct | Coverage@budget_lenient | 20 | 0.250 | 0.300 | 0.342 | -0.042 | -0.092 | +0.050 |
| self_correct | MRR@chunks | 20 | 0.225 | 0.300 | 0.375 | -0.075 | -0.150 | +0.075 |
| self_correct | ChunkHit@1 | 20 | 0.200 | 0.250 | 0.350 | -0.100 | -0.150 | +0.050 |
| self_correct | Precision@1 line | 20 | 0.150 | 0.200 | 0.050 | +0.150 | +0.100 | +0.050 |
| self_correct | Precision@3 line | 20 | 0.117 | 0.158 | 0.083 | +0.075 | +0.033 | +0.042 |
| self_correct | Precision@5 line | 20 | 0.117 | 0.158 | 0.077 | +0.082 | +0.040 | +0.042 |
| self_correct | MRR line | 20 | 0.200 | 0.275 | 0.162 | +0.113 | +0.038 | +0.075 |
| self_correct | Hit@5 line | 20 | 0.250 | 0.350 | 0.350 | +0.000 | -0.100 | +0.100 |
| self_correct | NDCG@10 line | 20 | 0.250 | 0.300 | 0.223 | +0.077 | +0.027 | +0.050 |
| self_correct | Coverage line | 20 | 0.250 | 0.300 | 0.342 | -0.042 | -0.092 | +0.050 |
| self_correct | Evidence chars | 20 | 484.500 | 497.600 | 499.350 | -1.750 | -14.850 | +13.100 |
| self_correct | Chunks kept | 20 | 1.950 | 2.200 | 1.250 | +0.950 | +0.700 | +0.250 |

## budget=1000 (n=77)

Hierarchical dense scoring mode: `content_only`.
Hierarchical retrieval mode: `routed_leaf_path`.
Route top sections: `3`.

Candidate pool path-depth check:
- Gold-hier: n=2779, path_depth_mean=2.184, max=5, hist={'1': 216, '2': 1841, '3': 719, '4': 1, '5': 2}
- Pred-hier: n=2329, path_depth_mean=1.851, max=5, hist={'1': 624, '2': 1436, '3': 263, '4': 4, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.181 | 0.207 | 0.318 | -0.111 | -0.137 | +0.026 |
| MRR@chunks | 0.216 | 0.225 | 0.398 | -0.173 | -0.182 | +0.009 |
| ChunkHit@1 | 0.182 | 0.182 | 0.364 | -0.182 | -0.182 | +0.000 |
| Precision@1 line | 0.143 | 0.117 | 0.065 | +0.052 | +0.078 | -0.026 |
| Precision@3 line | 0.104 | 0.110 | 0.061 | +0.050 | +0.043 | +0.006 |
| Precision@5 line | 0.110 | 0.107 | 0.068 | +0.039 | +0.042 | -0.003 |
| MRR line | 0.195 | 0.188 | 0.156 | +0.032 | +0.039 | -0.007 |
| Hit@5 line | 0.273 | 0.286 | 0.338 | -0.052 | -0.065 | +0.013 |
| NDCG@10 line | 0.168 | 0.177 | 0.172 | +0.005 | -0.004 | +0.009 |
| Coverage line | 0.181 | 0.207 | 0.318 | -0.111 | -0.137 | +0.026 |
| Evidence chars | 880.545 | 904.610 | 999.623 | -95.013 | -119.078 | +24.065 |
| Chunks kept | 2.519 | 2.545 | 2.091 | +0.455 | +0.429 | +0.026 |

### Per-type all metrics (budget=1000)

| task_type | Metric | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | Coverage@budget_lenient | 9 | 0.139 | 0.083 | 0.176 | -0.093 | -0.037 | -0.056 |
| cross_section_conflict | MRR@chunks | 9 | 0.333 | 0.148 | 0.444 | -0.296 | -0.111 | -0.185 |
| cross_section_conflict | ChunkHit@1 | 9 | 0.333 | 0.111 | 0.444 | -0.333 | -0.111 | -0.222 |
| cross_section_conflict | Precision@1 line | 9 | 0.333 | 0.111 | 0.222 | -0.111 | +0.111 | -0.222 |
| cross_section_conflict | Precision@3 line | 9 | 0.130 | 0.093 | 0.111 | -0.019 | +0.019 | -0.037 |
| cross_section_conflict | Precision@5 line | 9 | 0.130 | 0.083 | 0.089 | -0.006 | +0.041 | -0.046 |
| cross_section_conflict | MRR line | 9 | 0.333 | 0.148 | 0.281 | -0.133 | +0.052 | -0.185 |
| cross_section_conflict | Hit@5 line | 9 | 0.333 | 0.222 | 0.444 | -0.222 | -0.111 | -0.111 |
| cross_section_conflict | NDCG@10 line | 9 | 0.147 | 0.071 | 0.144 | -0.074 | +0.002 | -0.076 |
| cross_section_conflict | Coverage line | 9 | 0.139 | 0.083 | 0.176 | -0.093 | -0.037 | -0.056 |
| cross_section_conflict | Evidence chars | 9 | 925.444 | 917.111 | 1000.000 | -82.889 | -74.556 | -8.333 |
| cross_section_conflict | Chunks kept | 9 | 2.222 | 2.111 | 1.889 | +0.222 | +0.333 | -0.111 |
| multi_hop | Coverage@budget_lenient | 12 | 0.111 | 0.111 | 0.208 | -0.097 | -0.097 | +0.000 |
| multi_hop | MRR@chunks | 12 | 0.250 | 0.250 | 0.417 | -0.167 | -0.167 | +0.000 |
| multi_hop | ChunkHit@1 | 12 | 0.250 | 0.250 | 0.417 | -0.167 | -0.167 | +0.000 |
| multi_hop | Precision@1 line | 12 | 0.167 | 0.083 | 0.083 | +0.000 | +0.083 | -0.083 |
| multi_hop | Precision@3 line | 12 | 0.111 | 0.097 | 0.056 | +0.042 | +0.056 | -0.014 |
| multi_hop | Precision@5 line | 12 | 0.111 | 0.090 | 0.067 | +0.024 | +0.044 | -0.021 |
| multi_hop | MRR line | 12 | 0.208 | 0.167 | 0.159 | +0.008 | +0.049 | -0.042 |
| multi_hop | Hit@5 line | 12 | 0.250 | 0.250 | 0.333 | -0.083 | -0.083 | +0.000 |
| multi_hop | NDCG@10 line | 12 | 0.115 | 0.115 | 0.121 | -0.006 | -0.006 | +0.000 |
| multi_hop | Coverage line | 12 | 0.111 | 0.111 | 0.208 | -0.097 | -0.097 | +0.000 |
| multi_hop | Evidence chars | 12 | 913.750 | 931.750 | 1000.000 | -68.250 | -86.250 | +18.000 |
| multi_hop | Chunks kept | 12 | 2.250 | 2.333 | 1.583 | +0.750 | +0.667 | +0.083 |
| niche_fact | Coverage@budget_lenient | 21 | 0.206 | 0.206 | 0.397 | -0.190 | -0.190 | +0.000 |
| niche_fact | MRR@chunks | 21 | 0.167 | 0.167 | 0.421 | -0.254 | -0.254 | +0.000 |
| niche_fact | ChunkHit@1 | 21 | 0.095 | 0.095 | 0.381 | -0.286 | -0.286 | +0.000 |
| niche_fact | Precision@1 line | 21 | 0.048 | 0.048 | 0.048 | +0.000 | +0.000 | +0.000 |
| niche_fact | Precision@3 line | 21 | 0.095 | 0.095 | 0.032 | +0.063 | +0.063 | +0.000 |
| niche_fact | Precision@5 line | 21 | 0.105 | 0.105 | 0.067 | +0.038 | +0.038 | +0.000 |
| niche_fact | MRR line | 21 | 0.139 | 0.139 | 0.132 | +0.007 | +0.007 | +0.000 |
| niche_fact | Hit@5 line | 21 | 0.286 | 0.286 | 0.333 | -0.048 | -0.048 | +0.000 |
| niche_fact | NDCG@10 line | 21 | 0.169 | 0.169 | 0.188 | -0.019 | -0.019 | +0.000 |
| niche_fact | Coverage line | 21 | 0.206 | 0.206 | 0.397 | -0.190 | -0.190 | +0.000 |
| niche_fact | Evidence chars | 21 | 828.190 | 856.619 | 999.238 | -142.619 | -171.048 | +28.429 |
| niche_fact | Chunks kept | 21 | 2.762 | 2.667 | 2.048 | +0.619 | +0.714 | -0.095 |
| scope_collection | Coverage@budget_lenient | 15 | 0.067 | 0.167 | 0.250 | -0.083 | -0.183 | +0.100 |
| scope_collection | MRR@chunks | 15 | 0.133 | 0.222 | 0.289 | -0.067 | -0.156 | +0.089 |
| scope_collection | ChunkHit@1 | 15 | 0.133 | 0.200 | 0.267 | -0.067 | -0.133 | +0.067 |
| scope_collection | Precision@1 line | 15 | 0.133 | 0.133 | 0.000 | +0.133 | +0.133 | +0.000 |
| scope_collection | Precision@3 line | 15 | 0.067 | 0.111 | 0.044 | +0.067 | +0.022 | +0.044 |
| scope_collection | Precision@5 line | 15 | 0.067 | 0.106 | 0.057 | +0.049 | +0.010 | +0.039 |
| scope_collection | MRR line | 15 | 0.133 | 0.178 | 0.093 | +0.085 | +0.041 | +0.044 |
| scope_collection | Hit@5 line | 15 | 0.133 | 0.267 | 0.267 | +0.000 | -0.133 | +0.133 |
| scope_collection | NDCG@10 line | 15 | 0.076 | 0.139 | 0.129 | +0.010 | -0.053 | +0.063 |
| scope_collection | Coverage line | 15 | 0.067 | 0.167 | 0.250 | -0.083 | -0.183 | +0.100 |
| scope_collection | Evidence chars | 15 | 892.400 | 890.800 | 1000.000 | -109.200 | -107.600 | -1.600 |
| scope_collection | Chunks kept | 15 | 2.467 | 2.400 | 2.333 | +0.067 | +0.133 | -0.067 |
| self_correct | Coverage@budget_lenient | 20 | 0.300 | 0.350 | 0.417 | -0.067 | -0.117 | +0.050 |
| self_correct | MRR@chunks | 20 | 0.258 | 0.308 | 0.425 | -0.117 | -0.167 | +0.050 |
| self_correct | ChunkHit@1 | 20 | 0.200 | 0.250 | 0.350 | -0.100 | -0.150 | +0.050 |
| self_correct | Precision@1 line | 20 | 0.150 | 0.200 | 0.050 | +0.150 | +0.100 | +0.050 |
| self_correct | Precision@3 line | 20 | 0.125 | 0.142 | 0.083 | +0.058 | +0.042 | +0.017 |
| self_correct | Precision@5 line | 20 | 0.138 | 0.131 | 0.070 | +0.061 | +0.068 | -0.007 |
| self_correct | MRR line | 20 | 0.229 | 0.278 | 0.171 | +0.108 | +0.059 | +0.049 |
| self_correct | Hit@5 line | 20 | 0.350 | 0.350 | 0.350 | +0.000 | +0.000 | +0.000 |
| self_correct | NDCG@10 line | 20 | 0.278 | 0.300 | 0.230 | +0.070 | +0.048 | +0.022 |
| self_correct | Coverage line | 20 | 0.300 | 0.350 | 0.417 | -0.067 | -0.117 | +0.050 |
| self_correct | Evidence chars | 20 | 886.500 | 943.450 | 999.350 | -55.900 | -112.850 | +56.950 |
| self_correct | Chunks kept | 20 | 2.600 | 2.850 | 2.350 | +0.500 | +0.250 | +0.250 |

