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

- budget=300: 主指标 Coverage@budget_lenient 最好的是 Flat-react (0.113)；Pred-Flat=-0.024，Pred-Gold=-0.013；题级 Pred>Gold / Gold>Pred / Tie = 1/3/73。
- budget=500: 主指标 Coverage@budget_lenient 最好的是 Flat-react (0.246)；Pred-Flat=-0.104，Pred-Gold=-0.006；题级 Pred>Gold / Gold>Pred / Tie = 3/4/70。
- budget=1000: 主指标 Coverage@budget_lenient 最好的是 Flat-react (0.318)；Pred-Flat=-0.079，Pred-Gold=+0.026；题级 Pred>Gold / Gold>Pred / Tie = 5/4/68。
- Flat-react 在这些 budget 下整体强于 Pred-hier：Flat 更好的 budget=300, 500, 1000；打平 budget=-。
- Pred-hier 与 Gold-hier 的差异随 budget 改变：Pred 更好的 budget=1000；Gold 更好的 budget=300, 500；打平 budget=-。

按题型看主指标 Coverage@budget_lenient 的 Pred-Flat：

| Budget | Pred-hier 优于 Flat-react | 打平 | Flat-react 优于 Pred-hier |
| ---: | --- | --- | --- |
| 300 | multi_hop, niche_fact | - | cross_section_conflict, scope_collection, self_correct |
| 500 | multi_hop | - | cross_section_conflict, niche_fact, scope_collection, self_correct |
| 1000 | self_correct | - | cross_section_conflict, multi_hop, niche_fact, scope_collection |

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
Route top sections: `8`.

Candidate pool path-depth check:
- Gold-hier: n=5997, path_depth_mean=2.074, max=5, hist={'1': 563, '2': 4435, '3': 993, '4': 4, '5': 2}
- Pred-hier: n=5004, path_depth_mean=1.905, max=5, hist={'1': 1286, '2': 2962, '3': 704, '4': 50, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.102 | 0.089 | 0.113 | -0.024 | -0.011 | -0.013 |
| MRR@chunks | 0.156 | 0.130 | 0.195 | -0.065 | -0.039 | -0.026 |
| ChunkHit@1 | 0.156 | 0.130 | 0.195 | -0.065 | -0.039 | -0.026 |
| Precision@1 line | 0.143 | 0.104 | 0.065 | +0.039 | +0.078 | -0.039 |
| Precision@3 line | 0.130 | 0.102 | 0.043 | +0.058 | +0.087 | -0.028 |
| Precision@5 line | 0.130 | 0.100 | 0.045 | +0.055 | +0.085 | -0.030 |
| MRR line | 0.149 | 0.117 | 0.106 | +0.010 | +0.043 | -0.032 |
| Hit@5 line | 0.156 | 0.130 | 0.195 | -0.065 | -0.039 | -0.026 |
| NDCG@10 line | 0.104 | 0.091 | 0.092 | -0.001 | +0.012 | -0.013 |
| Coverage line | 0.102 | 0.089 | 0.113 | -0.024 | -0.011 | -0.013 |
| Evidence chars | 299.584 | 299.364 | 299.351 | +0.013 | +0.234 | -0.221 |
| Chunks kept | 1.429 | 1.351 | 1.039 | +0.312 | +0.390 | -0.078 |

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
| cross_section_conflict | Evidence chars | 9 | 298.222 | 297.778 | 299.222 | -1.444 | -1.000 | -0.444 |
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
| niche_fact | Coverage@budget_lenient | 21 | 0.095 | 0.095 | 0.071 | +0.024 | +0.024 | +0.000 |
| niche_fact | MRR@chunks | 21 | 0.095 | 0.095 | 0.095 | +0.000 | +0.000 | +0.000 |
| niche_fact | ChunkHit@1 | 21 | 0.095 | 0.095 | 0.095 | +0.000 | +0.000 | +0.000 |
| niche_fact | Precision@1 line | 21 | 0.048 | 0.048 | 0.048 | +0.000 | +0.000 | +0.000 |
| niche_fact | Precision@3 line | 21 | 0.071 | 0.063 | 0.016 | +0.048 | +0.056 | -0.008 |
| niche_fact | Precision@5 line | 21 | 0.071 | 0.057 | 0.021 | +0.036 | +0.050 | -0.014 |
| niche_fact | MRR line | 21 | 0.071 | 0.071 | 0.060 | +0.012 | +0.012 | +0.000 |
| niche_fact | Hit@5 line | 21 | 0.095 | 0.095 | 0.095 | +0.000 | +0.000 | +0.000 |
| niche_fact | NDCG@10 line | 21 | 0.095 | 0.095 | 0.060 | +0.036 | +0.036 | +0.000 |
| niche_fact | Coverage line | 21 | 0.095 | 0.095 | 0.071 | +0.024 | +0.024 | +0.000 |
| niche_fact | Evidence chars | 21 | 300.000 | 299.381 | 299.000 | +0.381 | +1.000 | -0.619 |
| niche_fact | Chunks kept | 21 | 1.571 | 1.429 | 1.048 | +0.381 | +0.524 | -0.143 |
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
| scope_collection | Chunks kept | 15 | 1.333 | 1.333 | 1.000 | +0.333 | +0.333 | +0.000 |
| self_correct | Coverage@budget_lenient | 20 | 0.150 | 0.150 | 0.192 | -0.042 | -0.042 | +0.000 |
| self_correct | MRR@chunks | 20 | 0.150 | 0.150 | 0.250 | -0.100 | -0.100 | +0.000 |
| self_correct | ChunkHit@1 | 20 | 0.150 | 0.150 | 0.250 | -0.100 | -0.100 | +0.000 |
| self_correct | Precision@1 line | 20 | 0.150 | 0.150 | 0.050 | +0.100 | +0.100 | +0.000 |
| self_correct | Precision@3 line | 20 | 0.100 | 0.100 | 0.067 | +0.033 | +0.033 | +0.000 |
| self_correct | Precision@5 line | 20 | 0.100 | 0.100 | 0.064 | +0.036 | +0.036 | +0.000 |
| self_correct | MRR line | 20 | 0.150 | 0.150 | 0.129 | +0.021 | +0.021 | +0.000 |
| self_correct | Hit@5 line | 20 | 0.150 | 0.150 | 0.250 | -0.100 | -0.100 | +0.000 |
| self_correct | NDCG@10 line | 20 | 0.150 | 0.150 | 0.166 | -0.016 | -0.016 | +0.000 |
| self_correct | Coverage line | 20 | 0.150 | 0.150 | 0.192 | -0.042 | -0.042 | +0.000 |
| self_correct | Evidence chars | 20 | 299.200 | 299.200 | 299.850 | -0.650 | -0.650 | +0.000 |
| self_correct | Chunks kept | 20 | 1.500 | 1.400 | 1.050 | +0.350 | +0.450 | -0.100 |

## budget=500 (n=77)

Hierarchical dense scoring mode: `content_only`.
Hierarchical retrieval mode: `routed_leaf_path`.
Route top sections: `8`.

Candidate pool path-depth check:
- Gold-hier: n=5997, path_depth_mean=2.074, max=5, hist={'1': 563, '2': 4435, '3': 993, '4': 4, '5': 2}
- Pred-hier: n=5004, path_depth_mean=1.905, max=5, hist={'1': 1286, '2': 2962, '3': 704, '4': 50, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.148 | 0.142 | 0.246 | -0.104 | -0.097 | -0.006 |
| MRR@chunks | 0.205 | 0.179 | 0.325 | -0.146 | -0.120 | -0.026 |
| ChunkHit@1 | 0.195 | 0.156 | 0.312 | -0.156 | -0.117 | -0.039 |
| Precision@1 line | 0.143 | 0.104 | 0.065 | +0.039 | +0.078 | -0.039 |
| Precision@3 line | 0.128 | 0.117 | 0.063 | +0.054 | +0.065 | -0.011 |
| Precision@5 line | 0.130 | 0.117 | 0.070 | +0.047 | +0.060 | -0.013 |
| MRR line | 0.179 | 0.153 | 0.143 | +0.009 | +0.035 | -0.026 |
| Hit@5 line | 0.221 | 0.208 | 0.312 | -0.104 | -0.091 | -0.013 |
| NDCG@10 line | 0.150 | 0.143 | 0.159 | -0.016 | -0.009 | -0.006 |
| Coverage line | 0.148 | 0.142 | 0.246 | -0.104 | -0.097 | -0.006 |
| Evidence chars | 499.831 | 499.623 | 499.195 | +0.429 | +0.636 | -0.208 |
| Chunks kept | 1.948 | 1.870 | 1.273 | +0.597 | +0.675 | -0.078 |

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
| cross_section_conflict | Evidence chars | 9 | 500.000 | 498.222 | 500.000 | -1.778 | +0.000 | -1.778 |
| cross_section_conflict | Chunks kept | 9 | 1.667 | 1.556 | 1.556 | +0.000 | +0.111 | -0.111 |
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
| niche_fact | Coverage@budget_lenient | 21 | 0.183 | 0.135 | 0.333 | -0.198 | -0.151 | -0.048 |
| niche_fact | MRR@chunks | 21 | 0.179 | 0.131 | 0.357 | -0.226 | -0.179 | -0.048 |
| niche_fact | ChunkHit@1 | 21 | 0.143 | 0.095 | 0.333 | -0.238 | -0.190 | -0.048 |
| niche_fact | Precision@1 line | 21 | 0.048 | 0.048 | 0.048 | +0.000 | +0.000 | +0.000 |
| niche_fact | Precision@3 line | 21 | 0.119 | 0.087 | 0.032 | +0.056 | +0.087 | -0.032 |
| niche_fact | Precision@5 line | 21 | 0.131 | 0.093 | 0.069 | +0.024 | +0.062 | -0.038 |
| niche_fact | MRR line | 21 | 0.131 | 0.107 | 0.123 | -0.016 | +0.008 | -0.024 |
| niche_fact | Hit@5 line | 21 | 0.238 | 0.190 | 0.333 | -0.143 | -0.095 | -0.048 |
| niche_fact | NDCG@10 line | 21 | 0.176 | 0.128 | 0.182 | -0.054 | -0.007 | -0.048 |
| niche_fact | Coverage line | 21 | 0.183 | 0.135 | 0.333 | -0.198 | -0.151 | -0.048 |
| niche_fact | Evidence chars | 21 | 499.381 | 499.381 | 500.000 | -0.619 | -0.619 | +0.000 |
| niche_fact | Chunks kept | 21 | 2.143 | 2.000 | 1.238 | +0.762 | +0.905 | -0.143 |
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
| scope_collection | Evidence chars | 15 | 500.000 | 500.000 | 498.133 | +1.867 | +1.867 | +0.000 |
| scope_collection | Chunks kept | 15 | 1.867 | 1.733 | 1.267 | +0.467 | +0.600 | -0.133 |
| self_correct | Coverage@budget_lenient | 20 | 0.200 | 0.275 | 0.342 | -0.067 | -0.142 | +0.075 |
| self_correct | MRR@chunks | 20 | 0.200 | 0.250 | 0.375 | -0.125 | -0.175 | +0.050 |
| self_correct | ChunkHit@1 | 20 | 0.200 | 0.200 | 0.350 | -0.150 | -0.150 | +0.000 |
| self_correct | Precision@1 line | 20 | 0.150 | 0.150 | 0.050 | +0.100 | +0.100 | +0.000 |
| self_correct | Precision@3 line | 20 | 0.092 | 0.142 | 0.083 | +0.058 | +0.008 | +0.050 |
| self_correct | Precision@5 line | 20 | 0.087 | 0.138 | 0.077 | +0.061 | +0.011 | +0.050 |
| self_correct | MRR line | 20 | 0.175 | 0.225 | 0.162 | +0.063 | +0.013 | +0.050 |
| self_correct | Hit@5 line | 20 | 0.200 | 0.300 | 0.350 | -0.050 | -0.150 | +0.100 |
| self_correct | NDCG@10 line | 20 | 0.200 | 0.275 | 0.223 | +0.052 | -0.023 | +0.075 |
| self_correct | Coverage line | 20 | 0.200 | 0.275 | 0.342 | -0.067 | -0.142 | +0.075 |
| self_correct | Evidence chars | 20 | 500.000 | 500.000 | 499.350 | +0.650 | +0.650 | +0.000 |
| self_correct | Chunks kept | 20 | 2.000 | 2.000 | 1.250 | +0.750 | +0.750 | +0.000 |

## budget=1000 (n=77)

Hierarchical dense scoring mode: `content_only`.
Hierarchical retrieval mode: `routed_leaf_path`.
Route top sections: `8`.

Candidate pool path-depth check:
- Gold-hier: n=5997, path_depth_mean=2.074, max=5, hist={'1': 563, '2': 4435, '3': 993, '4': 4, '5': 2}
- Pred-hier: n=5004, path_depth_mean=1.905, max=5, hist={'1': 1286, '2': 2962, '3': 704, '4': 50, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.213 | 0.239 | 0.318 | -0.079 | -0.105 | +0.026 |
| MRR@chunks | 0.242 | 0.242 | 0.398 | -0.156 | -0.156 | +0.000 |
| ChunkHit@1 | 0.208 | 0.195 | 0.364 | -0.169 | -0.156 | -0.013 |
| Precision@1 line | 0.143 | 0.104 | 0.065 | +0.039 | +0.078 | -0.039 |
| Precision@3 line | 0.113 | 0.115 | 0.061 | +0.054 | +0.052 | +0.002 |
| Precision@5 line | 0.109 | 0.104 | 0.068 | +0.035 | +0.041 | -0.006 |
| MRR line | 0.208 | 0.189 | 0.156 | +0.033 | +0.052 | -0.020 |
| Hit@5 line | 0.312 | 0.312 | 0.338 | -0.026 | -0.026 | +0.000 |
| NDCG@10 line | 0.192 | 0.199 | 0.172 | +0.027 | +0.020 | +0.007 |
| Coverage line | 0.213 | 0.239 | 0.318 | -0.079 | -0.105 | +0.026 |
| Evidence chars | 999.974 | 999.792 | 999.623 | +0.169 | +0.351 | -0.182 |
| Chunks kept | 3.156 | 3.156 | 2.091 | +1.065 | +1.065 | +0.000 |

### Per-type all metrics (budget=1000)

| task_type | Metric | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | Coverage@budget_lenient | 9 | 0.139 | 0.028 | 0.176 | -0.148 | -0.037 | -0.111 |
| cross_section_conflict | MRR@chunks | 9 | 0.333 | 0.111 | 0.444 | -0.333 | -0.111 | -0.222 |
| cross_section_conflict | ChunkHit@1 | 9 | 0.333 | 0.111 | 0.444 | -0.333 | -0.111 | -0.222 |
| cross_section_conflict | Precision@1 line | 9 | 0.333 | 0.111 | 0.222 | -0.111 | +0.111 | -0.222 |
| cross_section_conflict | Precision@3 line | 9 | 0.130 | 0.056 | 0.111 | -0.056 | +0.019 | -0.074 |
| cross_section_conflict | Precision@5 line | 9 | 0.130 | 0.056 | 0.089 | -0.033 | +0.041 | -0.074 |
| cross_section_conflict | MRR line | 9 | 0.333 | 0.111 | 0.281 | -0.170 | +0.052 | -0.222 |
| cross_section_conflict | Hit@5 line | 9 | 0.333 | 0.111 | 0.444 | -0.333 | -0.111 | -0.222 |
| cross_section_conflict | NDCG@10 line | 9 | 0.147 | 0.035 | 0.144 | -0.109 | +0.002 | -0.111 |
| cross_section_conflict | Coverage line | 9 | 0.139 | 0.028 | 0.176 | -0.148 | -0.037 | -0.111 |
| cross_section_conflict | Evidence chars | 9 | 1000.000 | 1000.000 | 1000.000 | +0.000 | +0.000 | +0.000 |
| cross_section_conflict | Chunks kept | 9 | 2.333 | 2.333 | 1.889 | +0.444 | +0.444 | +0.000 |
| multi_hop | Coverage@budget_lenient | 12 | 0.111 | 0.111 | 0.208 | -0.097 | -0.097 | +0.000 |
| multi_hop | MRR@chunks | 12 | 0.250 | 0.250 | 0.417 | -0.167 | -0.167 | +0.000 |
| multi_hop | ChunkHit@1 | 12 | 0.250 | 0.250 | 0.417 | -0.167 | -0.167 | +0.000 |
| multi_hop | Precision@1 line | 12 | 0.167 | 0.083 | 0.083 | +0.000 | +0.083 | -0.083 |
| multi_hop | Precision@3 line | 12 | 0.097 | 0.097 | 0.056 | +0.042 | +0.042 | +0.000 |
| multi_hop | Precision@5 line | 12 | 0.086 | 0.086 | 0.067 | +0.019 | +0.019 | +0.000 |
| multi_hop | MRR line | 12 | 0.208 | 0.167 | 0.159 | +0.008 | +0.049 | -0.042 |
| multi_hop | Hit@5 line | 12 | 0.250 | 0.250 | 0.333 | -0.083 | -0.083 | +0.000 |
| multi_hop | NDCG@10 line | 12 | 0.115 | 0.115 | 0.121 | -0.006 | -0.006 | +0.000 |
| multi_hop | Coverage line | 12 | 0.111 | 0.111 | 0.208 | -0.097 | -0.097 | +0.000 |
| multi_hop | Evidence chars | 12 | 1000.000 | 1000.000 | 1000.000 | +0.000 | +0.000 | +0.000 |
| multi_hop | Chunks kept | 12 | 3.000 | 3.000 | 1.583 | +1.417 | +1.417 | +0.000 |
| niche_fact | Coverage@budget_lenient | 21 | 0.254 | 0.254 | 0.397 | -0.143 | -0.143 | +0.000 |
| niche_fact | MRR@chunks | 21 | 0.204 | 0.204 | 0.421 | -0.217 | -0.217 | +0.000 |
| niche_fact | ChunkHit@1 | 21 | 0.143 | 0.143 | 0.381 | -0.238 | -0.238 | +0.000 |
| niche_fact | Precision@1 line | 21 | 0.048 | 0.048 | 0.048 | +0.000 | +0.000 | +0.000 |
| niche_fact | Precision@3 line | 21 | 0.103 | 0.095 | 0.032 | +0.063 | +0.071 | -0.008 |
| niche_fact | Precision@5 line | 21 | 0.118 | 0.104 | 0.067 | +0.037 | +0.052 | -0.014 |
| niche_fact | MRR line | 21 | 0.156 | 0.156 | 0.132 | +0.025 | +0.025 | +0.000 |
| niche_fact | Hit@5 line | 21 | 0.333 | 0.333 | 0.333 | +0.000 | +0.000 | +0.000 |
| niche_fact | NDCG@10 line | 21 | 0.211 | 0.211 | 0.188 | +0.023 | +0.023 | +0.000 |
| niche_fact | Coverage line | 21 | 0.254 | 0.254 | 0.397 | -0.143 | -0.143 | +0.000 |
| niche_fact | Evidence chars | 21 | 1000.000 | 1000.000 | 999.238 | +0.762 | +0.762 | +0.000 |
| niche_fact | Chunks kept | 21 | 3.381 | 3.571 | 2.048 | +1.524 | +1.333 | +0.190 |
| scope_collection | Coverage@budget_lenient | 15 | 0.100 | 0.167 | 0.250 | -0.083 | -0.150 | +0.067 |
| scope_collection | MRR@chunks | 15 | 0.156 | 0.222 | 0.289 | -0.067 | -0.133 | +0.067 |
| scope_collection | ChunkHit@1 | 15 | 0.133 | 0.200 | 0.267 | -0.067 | -0.133 | +0.067 |
| scope_collection | Precision@1 line | 15 | 0.133 | 0.133 | 0.000 | +0.133 | +0.133 | +0.000 |
| scope_collection | Precision@3 line | 15 | 0.089 | 0.111 | 0.044 | +0.067 | +0.044 | +0.022 |
| scope_collection | Precision@5 line | 15 | 0.063 | 0.077 | 0.057 | +0.020 | +0.007 | +0.013 |
| scope_collection | MRR line | 15 | 0.156 | 0.178 | 0.093 | +0.085 | +0.063 | +0.022 |
| scope_collection | Hit@5 line | 15 | 0.200 | 0.267 | 0.267 | +0.000 | -0.067 | +0.067 |
| scope_collection | NDCG@10 line | 15 | 0.097 | 0.139 | 0.129 | +0.010 | -0.032 | +0.042 |
| scope_collection | Coverage line | 15 | 0.100 | 0.167 | 0.250 | -0.083 | -0.150 | +0.067 |
| scope_collection | Evidence chars | 15 | 1000.000 | 998.933 | 1000.000 | -1.067 | +0.000 | -1.067 |
| scope_collection | Chunks kept | 15 | 3.400 | 3.067 | 2.333 | +0.733 | +1.067 | -0.333 |
| self_correct | Coverage@budget_lenient | 20 | 0.350 | 0.450 | 0.417 | +0.033 | -0.067 | +0.100 |
| self_correct | MRR@chunks | 20 | 0.300 | 0.350 | 0.425 | -0.075 | -0.125 | +0.050 |
| self_correct | ChunkHit@1 | 20 | 0.250 | 0.250 | 0.350 | -0.100 | -0.100 | +0.000 |
| self_correct | Precision@1 line | 20 | 0.150 | 0.150 | 0.050 | +0.100 | +0.100 | +0.000 |
| self_correct | Precision@3 line | 20 | 0.142 | 0.175 | 0.083 | +0.092 | +0.058 | +0.033 |
| self_correct | Precision@5 line | 20 | 0.139 | 0.156 | 0.070 | +0.086 | +0.069 | +0.017 |
| self_correct | MRR line | 20 | 0.246 | 0.278 | 0.171 | +0.108 | +0.075 | +0.033 |
| self_correct | Hit@5 line | 20 | 0.400 | 0.450 | 0.350 | +0.100 | +0.050 | +0.050 |
| self_correct | NDCG@10 line | 20 | 0.310 | 0.354 | 0.230 | +0.124 | +0.080 | +0.044 |
| self_correct | Coverage line | 20 | 0.350 | 0.450 | 0.417 | +0.033 | -0.067 | +0.100 |
| self_correct | Evidence chars | 20 | 999.900 | 1000.000 | 999.350 | +0.650 | +0.550 | +0.100 |
| self_correct | Chunks kept | 20 | 3.200 | 3.250 | 2.350 | +0.900 | +0.850 | +0.050 |

