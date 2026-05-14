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

- budget=300: 主指标 Coverage@budget_lenient 最好的是 Gold-hier (0.115)；Pred-Flat=+0.002，Pred-Gold=+0.000；题级 Pred>Gold / Gold>Pred / Tie = 2/3/72。
- budget=500: 主指标 Coverage@budget_lenient 最好的是 Flat-react (0.246)；Pred-Flat=-0.052，Pred-Gold=+0.013；题级 Pred>Gold / Gold>Pred / Tie = 2/2/73。
- budget=1000: 主指标 Coverage@budget_lenient 最好的是 Flat-react (0.318)；Pred-Flat=-0.034，Pred-Gold=+0.045；题级 Pred>Gold / Gold>Pred / Tie = 6/3/68。
- Pred-hier 相对 Flat-react 的收益不稳定：Pred 更好的 budget=300；Flat 更好的 budget=500, 1000；打平 budget=-。
- Pred-hier 平均不低于 Gold-hier：Pred 更好的 budget=500, 1000；打平 budget=300。差异主要来自少数题的 chunk 边界/路径文本变化。

按题型看主指标 Coverage@budget_lenient 的 Pred-Flat：

| Budget | Pred-hier 优于 Flat-react | 打平 | Flat-react 优于 Pred-hier |
| ---: | --- | --- | --- |
| 300 | multi_hop, niche_fact | - | cross_section_conflict, scope_collection, self_correct |
| 500 | multi_hop | - | cross_section_conflict, niche_fact, scope_collection, self_correct |
| 1000 | self_correct | niche_fact | cross_section_conflict, multi_hop, scope_collection |

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
Hierarchical retrieval mode: `multi_level_leaf_path_pool`.

Candidate pool path-depth check:
- Gold-hier: n=30761, path_depth_mean=1.697, max=5, hist={'1': 12632, '2': 14904, '3': 3130, '4': 93, '5': 2}
- Pred-hier: n=29868, path_depth_mean=1.669, max=5, hist={'1': 13445, '2': 13018, '3': 3248, '4': 155, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.115 | 0.115 | 0.113 | +0.002 | +0.002 | +0.000 |
| MRR@chunks | 0.169 | 0.156 | 0.195 | -0.039 | -0.026 | -0.013 |
| ChunkHit@1 | 0.169 | 0.156 | 0.195 | -0.039 | -0.026 | -0.013 |
| Precision@1 line | 0.130 | 0.117 | 0.065 | +0.052 | +0.065 | -0.013 |
| Precision@3 line | 0.136 | 0.121 | 0.043 | +0.078 | +0.093 | -0.015 |
| Precision@5 line | 0.136 | 0.119 | 0.045 | +0.074 | +0.091 | -0.017 |
| MRR line | 0.149 | 0.136 | 0.106 | +0.030 | +0.043 | -0.013 |
| Hit@5 line | 0.169 | 0.156 | 0.195 | -0.039 | -0.026 | -0.013 |
| NDCG@10 line | 0.117 | 0.117 | 0.092 | +0.025 | +0.025 | +0.000 |
| Coverage line | 0.115 | 0.115 | 0.113 | +0.002 | +0.002 | +0.000 |
| Evidence chars | 299.753 | 300.000 | 299.351 | +0.649 | +0.403 | +0.247 |
| Chunks kept | 1.416 | 1.377 | 1.039 | +0.338 | +0.377 | -0.039 |

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
| cross_section_conflict | Evidence chars | 9 | 300.000 | 300.000 | 299.222 | +0.778 | +0.778 | +0.000 |
| cross_section_conflict | Chunks kept | 9 | 1.111 | 1.000 | 1.111 | -0.111 | +0.000 | -0.111 |
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
| niche_fact | Coverage@budget_lenient | 21 | 0.143 | 0.238 | 0.071 | +0.167 | +0.071 | +0.095 |
| niche_fact | MRR@chunks | 21 | 0.143 | 0.238 | 0.095 | +0.143 | +0.048 | +0.095 |
| niche_fact | ChunkHit@1 | 21 | 0.143 | 0.238 | 0.095 | +0.143 | +0.048 | +0.095 |
| niche_fact | Precision@1 line | 21 | 0.048 | 0.143 | 0.048 | +0.095 | +0.000 | +0.095 |
| niche_fact | Precision@3 line | 21 | 0.095 | 0.159 | 0.016 | +0.143 | +0.079 | +0.063 |
| niche_fact | Precision@5 line | 21 | 0.095 | 0.152 | 0.021 | +0.131 | +0.074 | +0.057 |
| niche_fact | MRR line | 21 | 0.095 | 0.190 | 0.060 | +0.131 | +0.036 | +0.095 |
| niche_fact | Hit@5 line | 21 | 0.143 | 0.238 | 0.095 | +0.143 | +0.048 | +0.095 |
| niche_fact | NDCG@10 line | 21 | 0.143 | 0.238 | 0.060 | +0.179 | +0.083 | +0.095 |
| niche_fact | Coverage line | 21 | 0.143 | 0.238 | 0.071 | +0.167 | +0.071 | +0.095 |
| niche_fact | Evidence chars | 21 | 300.000 | 300.000 | 299.000 | +1.000 | +1.000 | +0.000 |
| niche_fact | Chunks kept | 21 | 1.667 | 1.571 | 1.048 | +0.524 | +0.619 | -0.095 |
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
| self_correct | Coverage@budget_lenient | 20 | 0.150 | 0.100 | 0.192 | -0.092 | -0.042 | -0.050 |
| self_correct | MRR@chunks | 20 | 0.150 | 0.100 | 0.250 | -0.150 | -0.100 | -0.050 |
| self_correct | ChunkHit@1 | 20 | 0.150 | 0.100 | 0.250 | -0.150 | -0.100 | -0.050 |
| self_correct | Precision@1 line | 20 | 0.100 | 0.100 | 0.050 | +0.050 | +0.050 | +0.000 |
| self_correct | Precision@3 line | 20 | 0.100 | 0.075 | 0.067 | +0.008 | +0.033 | -0.025 |
| self_correct | Precision@5 line | 20 | 0.100 | 0.075 | 0.064 | +0.011 | +0.036 | -0.025 |
| self_correct | MRR line | 20 | 0.125 | 0.100 | 0.129 | -0.029 | -0.004 | -0.025 |
| self_correct | Hit@5 line | 20 | 0.150 | 0.100 | 0.250 | -0.150 | -0.100 | -0.050 |
| self_correct | NDCG@10 line | 20 | 0.150 | 0.100 | 0.166 | -0.066 | -0.016 | -0.050 |
| self_correct | Coverage line | 20 | 0.150 | 0.100 | 0.192 | -0.092 | -0.042 | -0.050 |
| self_correct | Evidence chars | 20 | 299.050 | 300.000 | 299.850 | +0.150 | -0.800 | +0.950 |
| self_correct | Chunks kept | 20 | 1.400 | 1.400 | 1.050 | +0.350 | +0.350 | +0.000 |

## budget=500 (n=77)

Hierarchical dense scoring mode: `content_only`.
Hierarchical retrieval mode: `multi_level_leaf_path_pool`.

Candidate pool path-depth check:
- Gold-hier: n=30761, path_depth_mean=1.697, max=5, hist={'1': 12632, '2': 14904, '3': 3130, '4': 93, '5': 2}
- Pred-hier: n=29868, path_depth_mean=1.669, max=5, hist={'1': 13445, '2': 13018, '3': 3248, '4': 155, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.181 | 0.194 | 0.246 | -0.052 | -0.065 | +0.013 |
| MRR@chunks | 0.237 | 0.231 | 0.325 | -0.094 | -0.088 | -0.006 |
| ChunkHit@1 | 0.221 | 0.208 | 0.312 | -0.104 | -0.091 | -0.013 |
| Precision@1 line | 0.130 | 0.117 | 0.065 | +0.052 | +0.065 | -0.013 |
| Precision@3 line | 0.141 | 0.143 | 0.063 | +0.080 | +0.078 | +0.002 |
| Precision@5 line | 0.143 | 0.143 | 0.070 | +0.073 | +0.073 | +0.000 |
| MRR line | 0.187 | 0.181 | 0.143 | +0.038 | +0.044 | -0.006 |
| Hit@5 line | 0.260 | 0.260 | 0.312 | -0.052 | -0.052 | +0.000 |
| NDCG@10 line | 0.175 | 0.188 | 0.159 | +0.029 | +0.016 | +0.013 |
| Coverage line | 0.181 | 0.194 | 0.246 | -0.052 | -0.065 | +0.013 |
| Evidence chars | 499.831 | 499.623 | 499.195 | +0.429 | +0.636 | -0.208 |
| Chunks kept | 1.883 | 1.818 | 1.273 | +0.545 | +0.610 | -0.065 |

### Per-type all metrics (budget=500)

| task_type | Metric | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | Coverage@budget_lenient | 9 | 0.194 | 0.083 | 0.176 | -0.093 | +0.019 | -0.111 |
| cross_section_conflict | MRR@chunks | 9 | 0.444 | 0.222 | 0.444 | -0.222 | +0.000 | -0.222 |
| cross_section_conflict | ChunkHit@1 | 9 | 0.444 | 0.222 | 0.444 | -0.222 | +0.000 | -0.222 |
| cross_section_conflict | Precision@1 line | 9 | 0.333 | 0.111 | 0.222 | -0.111 | +0.111 | -0.222 |
| cross_section_conflict | Precision@3 line | 9 | 0.259 | 0.148 | 0.111 | +0.037 | +0.148 | -0.111 |
| cross_section_conflict | Precision@5 line | 9 | 0.259 | 0.139 | 0.094 | +0.044 | +0.165 | -0.120 |
| cross_section_conflict | MRR line | 9 | 0.370 | 0.148 | 0.281 | -0.133 | +0.089 | -0.222 |
| cross_section_conflict | Hit@5 line | 9 | 0.444 | 0.222 | 0.444 | -0.222 | +0.000 | -0.222 |
| cross_section_conflict | NDCG@10 line | 9 | 0.182 | 0.071 | 0.144 | -0.074 | +0.038 | -0.111 |
| cross_section_conflict | Coverage line | 9 | 0.194 | 0.083 | 0.176 | -0.093 | +0.019 | -0.111 |
| cross_section_conflict | Evidence chars | 9 | 500.000 | 498.222 | 500.000 | -1.778 | +0.000 | -1.778 |
| cross_section_conflict | Chunks kept | 9 | 1.333 | 1.222 | 1.556 | -0.333 | -0.222 | -0.111 |
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
| niche_fact | Coverage@budget_lenient | 21 | 0.230 | 0.278 | 0.333 | -0.056 | -0.103 | +0.048 |
| niche_fact | MRR@chunks | 21 | 0.226 | 0.274 | 0.357 | -0.083 | -0.131 | +0.048 |
| niche_fact | ChunkHit@1 | 21 | 0.190 | 0.238 | 0.333 | -0.095 | -0.143 | +0.048 |
| niche_fact | Precision@1 line | 21 | 0.048 | 0.143 | 0.048 | +0.095 | +0.000 | +0.095 |
| niche_fact | Precision@3 line | 21 | 0.135 | 0.167 | 0.032 | +0.135 | +0.103 | +0.032 |
| niche_fact | Precision@5 line | 21 | 0.147 | 0.172 | 0.069 | +0.103 | +0.078 | +0.025 |
| niche_fact | MRR line | 21 | 0.155 | 0.226 | 0.123 | +0.103 | +0.032 | +0.071 |
| niche_fact | Hit@5 line | 21 | 0.286 | 0.333 | 0.333 | +0.000 | -0.048 | +0.048 |
| niche_fact | NDCG@10 line | 21 | 0.223 | 0.271 | 0.182 | +0.089 | +0.041 | +0.048 |
| niche_fact | Coverage line | 21 | 0.230 | 0.278 | 0.333 | -0.056 | -0.103 | +0.048 |
| niche_fact | Evidence chars | 21 | 499.381 | 499.381 | 500.000 | -0.619 | -0.619 | +0.000 |
| niche_fact | Chunks kept | 21 | 2.190 | 2.095 | 1.238 | +0.857 | +0.952 | -0.095 |
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
| scope_collection | Chunks kept | 15 | 1.800 | 1.733 | 1.267 | +0.467 | +0.533 | -0.067 |
| self_correct | Coverage@budget_lenient | 20 | 0.250 | 0.300 | 0.342 | -0.042 | -0.092 | +0.050 |
| self_correct | MRR@chunks | 20 | 0.225 | 0.250 | 0.375 | -0.125 | -0.150 | +0.025 |
| self_correct | ChunkHit@1 | 20 | 0.200 | 0.200 | 0.350 | -0.150 | -0.150 | +0.000 |
| self_correct | Precision@1 line | 20 | 0.100 | 0.100 | 0.050 | +0.050 | +0.050 | +0.000 |
| self_correct | Precision@3 line | 20 | 0.108 | 0.142 | 0.083 | +0.058 | +0.025 | +0.033 |
| self_correct | Precision@5 line | 20 | 0.104 | 0.142 | 0.077 | +0.065 | +0.027 | +0.037 |
| self_correct | MRR line | 20 | 0.167 | 0.192 | 0.162 | +0.029 | +0.004 | +0.025 |
| self_correct | Hit@5 line | 20 | 0.250 | 0.300 | 0.350 | -0.050 | -0.100 | +0.050 |
| self_correct | NDCG@10 line | 20 | 0.232 | 0.282 | 0.223 | +0.059 | +0.009 | +0.050 |
| self_correct | Coverage line | 20 | 0.250 | 0.300 | 0.342 | -0.042 | -0.092 | +0.050 |
| self_correct | Evidence chars | 20 | 500.000 | 500.000 | 499.350 | +0.650 | +0.650 | +0.000 |
| self_correct | Chunks kept | 20 | 1.900 | 1.850 | 1.250 | +0.600 | +0.650 | -0.050 |

## budget=1000 (n=77)

Hierarchical dense scoring mode: `content_only`.
Hierarchical retrieval mode: `multi_level_leaf_path_pool`.

Candidate pool path-depth check:
- Gold-hier: n=30761, path_depth_mean=1.697, max=5, hist={'1': 12632, '2': 14904, '3': 3130, '4': 93, '5': 2}
- Pred-hier: n=29868, path_depth_mean=1.669, max=5, hist={'1': 13445, '2': 13018, '3': 3248, '4': 155, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.239 | 0.285 | 0.318 | -0.034 | -0.079 | +0.045 |
| MRR@chunks | 0.268 | 0.290 | 0.398 | -0.108 | -0.131 | +0.023 |
| ChunkHit@1 | 0.234 | 0.247 | 0.364 | -0.117 | -0.130 | +0.013 |
| Precision@1 line | 0.130 | 0.117 | 0.065 | +0.052 | +0.065 | -0.013 |
| Precision@3 line | 0.113 | 0.123 | 0.061 | +0.063 | +0.052 | +0.011 |
| Precision@5 line | 0.114 | 0.121 | 0.068 | +0.053 | +0.046 | +0.008 |
| MRR line | 0.209 | 0.213 | 0.156 | +0.057 | +0.053 | +0.004 |
| Hit@5 line | 0.338 | 0.364 | 0.338 | +0.026 | +0.000 | +0.026 |
| NDCG@10 line | 0.209 | 0.236 | 0.172 | +0.064 | +0.037 | +0.027 |
| Coverage line | 0.239 | 0.285 | 0.318 | -0.034 | -0.079 | +0.045 |
| Evidence chars | 1000.000 | 1000.000 | 999.623 | +0.377 | +0.377 | +0.000 |
| Chunks kept | 2.870 | 2.909 | 2.091 | +0.818 | +0.779 | +0.039 |

### Per-type all metrics (budget=1000)

| task_type | Metric | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | Coverage@budget_lenient | 9 | 0.194 | 0.083 | 0.176 | -0.093 | +0.019 | -0.111 |
| cross_section_conflict | MRR@chunks | 9 | 0.444 | 0.222 | 0.444 | -0.222 | +0.000 | -0.222 |
| cross_section_conflict | ChunkHit@1 | 9 | 0.444 | 0.222 | 0.444 | -0.222 | +0.000 | -0.222 |
| cross_section_conflict | Precision@1 line | 9 | 0.333 | 0.111 | 0.222 | -0.111 | +0.111 | -0.222 |
| cross_section_conflict | Precision@3 line | 9 | 0.167 | 0.093 | 0.111 | -0.019 | +0.056 | -0.074 |
| cross_section_conflict | Precision@5 line | 9 | 0.152 | 0.078 | 0.089 | -0.011 | +0.063 | -0.074 |
| cross_section_conflict | MRR line | 9 | 0.370 | 0.148 | 0.281 | -0.133 | +0.089 | -0.222 |
| cross_section_conflict | Hit@5 line | 9 | 0.444 | 0.222 | 0.444 | -0.222 | +0.000 | -0.222 |
| cross_section_conflict | NDCG@10 line | 9 | 0.182 | 0.071 | 0.144 | -0.074 | +0.038 | -0.111 |
| cross_section_conflict | Coverage line | 9 | 0.194 | 0.083 | 0.176 | -0.093 | +0.019 | -0.111 |
| cross_section_conflict | Evidence chars | 9 | 1000.000 | 1000.000 | 1000.000 | +0.000 | +0.000 | +0.000 |
| cross_section_conflict | Chunks kept | 9 | 1.889 | 1.889 | 1.889 | +0.000 | +0.000 | +0.000 |
| multi_hop | Coverage@budget_lenient | 12 | 0.153 | 0.153 | 0.208 | -0.056 | -0.056 | +0.000 |
| multi_hop | MRR@chunks | 12 | 0.278 | 0.278 | 0.417 | -0.139 | -0.139 | +0.000 |
| multi_hop | ChunkHit@1 | 12 | 0.250 | 0.250 | 0.417 | -0.167 | -0.167 | +0.000 |
| multi_hop | Precision@1 line | 12 | 0.167 | 0.083 | 0.083 | +0.000 | +0.083 | -0.083 |
| multi_hop | Precision@3 line | 12 | 0.111 | 0.097 | 0.056 | +0.042 | +0.056 | -0.014 |
| multi_hop | Precision@5 line | 12 | 0.121 | 0.107 | 0.067 | +0.040 | +0.054 | -0.014 |
| multi_hop | MRR line | 12 | 0.229 | 0.188 | 0.159 | +0.028 | +0.070 | -0.042 |
| multi_hop | Hit@5 line | 12 | 0.333 | 0.333 | 0.333 | +0.000 | +0.000 | +0.000 |
| multi_hop | NDCG@10 line | 12 | 0.136 | 0.136 | 0.121 | +0.015 | +0.015 | +0.000 |
| multi_hop | Coverage line | 12 | 0.153 | 0.153 | 0.208 | -0.056 | -0.056 | +0.000 |
| multi_hop | Evidence chars | 12 | 1000.000 | 1000.000 | 1000.000 | +0.000 | +0.000 | +0.000 |
| multi_hop | Chunks kept | 12 | 2.833 | 2.833 | 1.583 | +1.250 | +1.250 | +0.000 |
| niche_fact | Coverage@budget_lenient | 21 | 0.302 | 0.397 | 0.397 | +0.000 | -0.095 | +0.095 |
| niche_fact | MRR@chunks | 21 | 0.252 | 0.347 | 0.421 | -0.074 | -0.169 | +0.095 |
| niche_fact | ChunkHit@1 | 21 | 0.190 | 0.286 | 0.381 | -0.095 | -0.190 | +0.095 |
| niche_fact | Precision@1 line | 21 | 0.048 | 0.143 | 0.048 | +0.095 | +0.000 | +0.095 |
| niche_fact | Precision@3 line | 21 | 0.111 | 0.159 | 0.032 | +0.127 | +0.079 | +0.048 |
| niche_fact | Precision@5 line | 21 | 0.120 | 0.157 | 0.067 | +0.090 | +0.053 | +0.037 |
| niche_fact | MRR line | 21 | 0.180 | 0.275 | 0.132 | +0.144 | +0.049 | +0.095 |
| niche_fact | Hit@5 line | 21 | 0.381 | 0.476 | 0.333 | +0.143 | +0.048 | +0.095 |
| niche_fact | NDCG@10 line | 21 | 0.259 | 0.354 | 0.188 | +0.166 | +0.071 | +0.095 |
| niche_fact | Coverage line | 21 | 0.302 | 0.397 | 0.397 | +0.000 | -0.095 | +0.095 |
| niche_fact | Evidence chars | 21 | 1000.000 | 1000.000 | 999.238 | +0.762 | +0.762 | +0.000 |
| niche_fact | Chunks kept | 21 | 3.429 | 3.667 | 2.048 | +1.619 | +1.381 | +0.238 |
| scope_collection | Coverage@budget_lenient | 15 | 0.067 | 0.133 | 0.250 | -0.117 | -0.183 | +0.067 |
| scope_collection | MRR@chunks | 15 | 0.133 | 0.200 | 0.289 | -0.089 | -0.156 | +0.067 |
| scope_collection | ChunkHit@1 | 15 | 0.133 | 0.200 | 0.267 | -0.067 | -0.133 | +0.067 |
| scope_collection | Precision@1 line | 15 | 0.133 | 0.133 | 0.000 | +0.133 | +0.133 | +0.000 |
| scope_collection | Precision@3 line | 15 | 0.067 | 0.089 | 0.044 | +0.044 | +0.022 | +0.022 |
| scope_collection | Precision@5 line | 15 | 0.050 | 0.067 | 0.057 | +0.010 | -0.007 | +0.017 |
| scope_collection | MRR line | 15 | 0.133 | 0.156 | 0.093 | +0.063 | +0.041 | +0.022 |
| scope_collection | Hit@5 line | 15 | 0.133 | 0.200 | 0.267 | -0.067 | -0.133 | +0.067 |
| scope_collection | NDCG@10 line | 15 | 0.076 | 0.118 | 0.129 | -0.011 | -0.053 | +0.042 |
| scope_collection | Coverage line | 15 | 0.067 | 0.133 | 0.250 | -0.117 | -0.183 | +0.067 |
| scope_collection | Evidence chars | 15 | 1000.000 | 1000.000 | 1000.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | Chunks kept | 15 | 2.733 | 2.600 | 2.333 | +0.267 | +0.400 | -0.133 |
| self_correct | Coverage@budget_lenient | 20 | 0.375 | 0.450 | 0.417 | +0.033 | -0.042 | +0.075 |
| self_correct | MRR@chunks | 20 | 0.300 | 0.338 | 0.425 | -0.087 | -0.125 | +0.038 |
| self_correct | ChunkHit@1 | 20 | 0.250 | 0.250 | 0.350 | -0.100 | -0.100 | +0.000 |
| self_correct | Precision@1 line | 20 | 0.100 | 0.100 | 0.050 | +0.050 | +0.050 | +0.000 |
| self_correct | Precision@3 line | 20 | 0.125 | 0.142 | 0.083 | +0.058 | +0.042 | +0.017 |
| self_correct | Precision@5 line | 20 | 0.134 | 0.153 | 0.070 | +0.083 | +0.064 | +0.019 |
| self_correct | MRR line | 20 | 0.212 | 0.234 | 0.171 | +0.064 | +0.041 | +0.022 |
| self_correct | Hit@5 line | 20 | 0.400 | 0.450 | 0.350 | +0.100 | +0.050 | +0.050 |
| self_correct | NDCG@10 line | 20 | 0.314 | 0.336 | 0.230 | +0.106 | +0.084 | +0.023 |
| self_correct | Coverage line | 20 | 0.375 | 0.450 | 0.417 | +0.033 | -0.042 | +0.075 |
| self_correct | Evidence chars | 20 | 1000.000 | 1000.000 | 999.350 | +0.650 | +0.650 | +0.000 |
| self_correct | Chunks kept | 20 | 2.850 | 2.850 | 2.350 | +0.500 | +0.500 | +0.000 |

