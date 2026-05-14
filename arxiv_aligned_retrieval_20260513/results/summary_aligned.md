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

- budget=300: 主指标 Coverage@budget_lenient 最好的是 Pred-hier (0.132)；Pred-Flat=+0.019，Pred-Gold=+0.016；题级 Pred>Gold / Gold>Pred / Tie = 4/2/71。
- budget=500: 主指标 Coverage@budget_lenient 最好的是 Flat-react (0.246)；Pred-Flat=-0.045，Pred-Gold=+0.029；题级 Pred>Gold / Gold>Pred / Tie = 4/1/72。
- budget=1000: 主指标 Coverage@budget_lenient 最好的是 Flat-react (0.318)；Pred-Flat=-0.053，Pred-Gold=+0.049；题级 Pred>Gold / Gold>Pred / Tie = 5/2/70。
- Pred-hier 相对 Flat-react 的收益不稳定：Pred 更好的 budget=300；Flat 更好的 budget=500, 1000；打平 budget=-。
- Pred-hier 平均不低于 Gold-hier：Pred 更好的 budget=300, 500, 1000；打平 budget=-。差异主要来自少数题的 chunk 边界/路径文本变化。

按题型看主指标 Coverage@budget_lenient 的 Pred-Flat：

| Budget | Pred-hier 优于 Flat-react | 打平 | Flat-react 优于 Pred-hier |
| ---: | --- | --- | --- |
| 300 | multi_hop, niche_fact | - | cross_section_conflict, scope_collection, self_correct |
| 500 | multi_hop | - | cross_section_conflict, niche_fact, scope_collection, self_correct |
| 1000 | - | niche_fact | cross_section_conflict, multi_hop, scope_collection, self_correct |

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

Hierarchical dense scoring mode: `full_text`.
Hierarchical retrieval mode: `multi_level_leaf_path_pool`.

Candidate pool path-depth check:
- Gold-hier: n=30761, path_depth_mean=1.697, max=5, hist={'1': 12632, '2': 14904, '3': 3130, '4': 93, '5': 2}
- Pred-hier: n=29868, path_depth_mean=1.669, max=5, hist={'1': 13445, '2': 13018, '3': 3248, '4': 155, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.116 | 0.132 | 0.113 | +0.019 | +0.003 | +0.016 |
| MRR@chunks | 0.169 | 0.195 | 0.195 | +0.000 | -0.026 | +0.026 |
| ChunkHit@1 | 0.169 | 0.195 | 0.195 | +0.000 | -0.026 | +0.026 |
| Precision@1 line | 0.117 | 0.156 | 0.065 | +0.091 | +0.052 | +0.039 |
| Precision@3 line | 0.130 | 0.145 | 0.043 | +0.102 | +0.087 | +0.015 |
| Precision@5 line | 0.130 | 0.143 | 0.045 | +0.098 | +0.085 | +0.013 |
| MRR line | 0.143 | 0.175 | 0.106 | +0.069 | +0.036 | +0.032 |
| Hit@5 line | 0.169 | 0.195 | 0.195 | +0.000 | -0.026 | +0.026 |
| NDCG@10 line | 0.118 | 0.135 | 0.092 | +0.043 | +0.026 | +0.017 |
| Coverage line | 0.116 | 0.132 | 0.113 | +0.019 | +0.003 | +0.016 |
| Evidence chars | 300.000 | 300.000 | 299.351 | +0.649 | +0.649 | +0.000 |
| Chunks kept | 1.299 | 1.299 | 1.039 | +0.260 | +0.260 | +0.000 |

### Per-type all metrics (budget=300)

| task_type | Metric | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | Coverage@budget_lenient | 9 | 0.111 | 0.139 | 0.176 | -0.037 | -0.065 | +0.028 |
| cross_section_conflict | MRR@chunks | 9 | 0.222 | 0.333 | 0.444 | -0.111 | -0.222 | +0.111 |
| cross_section_conflict | ChunkHit@1 | 9 | 0.222 | 0.333 | 0.444 | -0.111 | -0.222 | +0.111 |
| cross_section_conflict | Precision@1 line | 9 | 0.222 | 0.333 | 0.222 | +0.111 | +0.000 | +0.111 |
| cross_section_conflict | Precision@3 line | 9 | 0.167 | 0.204 | 0.111 | +0.093 | +0.056 | +0.037 |
| cross_section_conflict | Precision@5 line | 9 | 0.167 | 0.204 | 0.104 | +0.100 | +0.063 | +0.037 |
| cross_section_conflict | MRR line | 9 | 0.222 | 0.333 | 0.281 | +0.052 | -0.059 | +0.111 |
| cross_section_conflict | Hit@5 line | 9 | 0.222 | 0.333 | 0.444 | -0.111 | -0.222 | +0.111 |
| cross_section_conflict | NDCG@10 line | 9 | 0.111 | 0.147 | 0.144 | +0.002 | -0.033 | +0.035 |
| cross_section_conflict | Coverage line | 9 | 0.111 | 0.139 | 0.176 | -0.037 | -0.065 | +0.028 |
| cross_section_conflict | Evidence chars | 9 | 300.000 | 300.000 | 299.222 | +0.778 | +0.778 | +0.000 |
| cross_section_conflict | Chunks kept | 9 | 1.111 | 1.222 | 1.111 | +0.111 | +0.000 | +0.111 |
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
| multi_hop | Chunks kept | 12 | 1.250 | 1.250 | 1.000 | +0.250 | +0.250 | +0.000 |
| niche_fact | Coverage@budget_lenient | 21 | 0.206 | 0.254 | 0.071 | +0.183 | +0.135 | +0.048 |
| niche_fact | MRR@chunks | 21 | 0.238 | 0.286 | 0.095 | +0.190 | +0.143 | +0.048 |
| niche_fact | ChunkHit@1 | 21 | 0.238 | 0.286 | 0.095 | +0.190 | +0.143 | +0.048 |
| niche_fact | Precision@1 line | 21 | 0.095 | 0.190 | 0.048 | +0.143 | +0.048 | +0.095 |
| niche_fact | Precision@3 line | 21 | 0.167 | 0.206 | 0.016 | +0.190 | +0.151 | +0.040 |
| niche_fact | Precision@5 line | 21 | 0.167 | 0.200 | 0.021 | +0.179 | +0.145 | +0.033 |
| niche_fact | MRR line | 21 | 0.167 | 0.238 | 0.060 | +0.179 | +0.107 | +0.071 |
| niche_fact | Hit@5 line | 21 | 0.238 | 0.286 | 0.095 | +0.190 | +0.143 | +0.048 |
| niche_fact | NDCG@10 line | 21 | 0.209 | 0.256 | 0.060 | +0.197 | +0.149 | +0.048 |
| niche_fact | Coverage line | 21 | 0.206 | 0.254 | 0.071 | +0.183 | +0.135 | +0.048 |
| niche_fact | Evidence chars | 21 | 300.000 | 300.000 | 299.000 | +1.000 | +1.000 | +0.000 |
| niche_fact | Chunks kept | 21 | 1.381 | 1.429 | 1.048 | +0.381 | +0.333 | +0.048 |
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
| scope_collection | Chunks kept | 15 | 1.267 | 1.267 | 1.000 | +0.267 | +0.267 | +0.000 |
| self_correct | Coverage@budget_lenient | 20 | 0.100 | 0.100 | 0.192 | -0.092 | -0.092 | +0.000 |
| self_correct | MRR@chunks | 20 | 0.100 | 0.100 | 0.250 | -0.150 | -0.150 | +0.000 |
| self_correct | ChunkHit@1 | 20 | 0.100 | 0.100 | 0.250 | -0.150 | -0.150 | +0.000 |
| self_correct | Precision@1 line | 20 | 0.050 | 0.100 | 0.050 | +0.050 | +0.000 | +0.050 |
| self_correct | Precision@3 line | 20 | 0.050 | 0.075 | 0.067 | +0.008 | -0.017 | +0.025 |
| self_correct | Precision@5 line | 20 | 0.050 | 0.075 | 0.064 | +0.011 | -0.014 | +0.025 |
| self_correct | MRR line | 20 | 0.075 | 0.100 | 0.129 | -0.029 | -0.054 | +0.025 |
| self_correct | Hit@5 line | 20 | 0.100 | 0.100 | 0.250 | -0.150 | -0.150 | +0.000 |
| self_correct | NDCG@10 line | 20 | 0.100 | 0.100 | 0.166 | -0.066 | -0.066 | +0.000 |
| self_correct | Coverage line | 20 | 0.100 | 0.100 | 0.192 | -0.092 | -0.092 | +0.000 |
| self_correct | Evidence chars | 20 | 300.000 | 300.000 | 299.850 | +0.150 | +0.150 | +0.000 |
| self_correct | Chunks kept | 20 | 1.350 | 1.250 | 1.050 | +0.200 | +0.300 | -0.100 |

## budget=500 (n=77)

Hierarchical dense scoring mode: `full_text`.
Hierarchical retrieval mode: `multi_level_leaf_path_pool`.

Candidate pool path-depth check:
- Gold-hier: n=30761, path_depth_mean=1.697, max=5, hist={'1': 12632, '2': 14904, '3': 3130, '4': 93, '5': 2}
- Pred-hier: n=29868, path_depth_mean=1.669, max=5, hist={'1': 13445, '2': 13018, '3': 3248, '4': 155, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.171 | 0.200 | 0.246 | -0.045 | -0.075 | +0.029 |
| MRR@chunks | 0.221 | 0.253 | 0.325 | -0.071 | -0.104 | +0.032 |
| ChunkHit@1 | 0.208 | 0.234 | 0.312 | -0.078 | -0.104 | +0.026 |
| Precision@1 line | 0.117 | 0.156 | 0.065 | +0.091 | +0.052 | +0.039 |
| Precision@3 line | 0.126 | 0.152 | 0.063 | +0.089 | +0.063 | +0.026 |
| Precision@5 line | 0.126 | 0.150 | 0.070 | +0.080 | +0.056 | +0.024 |
| MRR line | 0.173 | 0.212 | 0.143 | +0.069 | +0.030 | +0.039 |
| Hit@5 line | 0.234 | 0.273 | 0.312 | -0.039 | -0.078 | +0.039 |
| NDCG@10 line | 0.169 | 0.199 | 0.159 | +0.040 | +0.010 | +0.030 |
| Coverage line | 0.171 | 0.200 | 0.246 | -0.045 | -0.075 | +0.029 |
| Evidence chars | 499.455 | 499.844 | 499.195 | +0.649 | +0.260 | +0.390 |
| Chunks kept | 1.805 | 1.779 | 1.273 | +0.506 | +0.532 | -0.026 |

### Per-type all metrics (budget=500)

| task_type | Metric | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | Coverage@budget_lenient | 9 | 0.111 | 0.139 | 0.176 | -0.037 | -0.065 | +0.028 |
| cross_section_conflict | MRR@chunks | 9 | 0.222 | 0.333 | 0.444 | -0.111 | -0.222 | +0.111 |
| cross_section_conflict | ChunkHit@1 | 9 | 0.222 | 0.333 | 0.444 | -0.111 | -0.222 | +0.111 |
| cross_section_conflict | Precision@1 line | 9 | 0.222 | 0.333 | 0.222 | +0.111 | +0.000 | +0.111 |
| cross_section_conflict | Precision@3 line | 9 | 0.111 | 0.185 | 0.111 | +0.074 | +0.000 | +0.074 |
| cross_section_conflict | Precision@5 line | 9 | 0.111 | 0.185 | 0.094 | +0.091 | +0.017 | +0.074 |
| cross_section_conflict | MRR line | 9 | 0.222 | 0.333 | 0.281 | +0.052 | -0.059 | +0.111 |
| cross_section_conflict | Hit@5 line | 9 | 0.222 | 0.333 | 0.444 | -0.111 | -0.222 | +0.111 |
| cross_section_conflict | NDCG@10 line | 9 | 0.111 | 0.147 | 0.144 | +0.002 | -0.033 | +0.035 |
| cross_section_conflict | Coverage line | 9 | 0.111 | 0.139 | 0.176 | -0.037 | -0.065 | +0.028 |
| cross_section_conflict | Evidence chars | 9 | 500.000 | 500.000 | 500.000 | +0.000 | +0.000 | +0.000 |
| cross_section_conflict | Chunks kept | 9 | 1.444 | 1.444 | 1.556 | -0.111 | -0.111 | +0.000 |
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
| multi_hop | Evidence chars | 12 | 498.333 | 499.333 | 498.250 | +1.083 | +0.083 | +1.000 |
| multi_hop | Chunks kept | 12 | 1.500 | 1.500 | 1.167 | +0.333 | +0.333 | +0.000 |
| niche_fact | Coverage@budget_lenient | 21 | 0.278 | 0.278 | 0.333 | -0.056 | -0.056 | +0.000 |
| niche_fact | MRR@chunks | 21 | 0.310 | 0.310 | 0.357 | -0.048 | -0.048 | +0.000 |
| niche_fact | ChunkHit@1 | 21 | 0.286 | 0.286 | 0.333 | -0.048 | -0.048 | +0.000 |
| niche_fact | Precision@1 line | 21 | 0.095 | 0.190 | 0.048 | +0.143 | +0.048 | +0.095 |
| niche_fact | Precision@3 line | 21 | 0.167 | 0.183 | 0.032 | +0.151 | +0.135 | +0.016 |
| niche_fact | Precision@5 line | 21 | 0.167 | 0.176 | 0.069 | +0.107 | +0.098 | +0.010 |
| niche_fact | MRR line | 21 | 0.214 | 0.262 | 0.123 | +0.139 | +0.091 | +0.048 |
| niche_fact | Hit@5 line | 21 | 0.333 | 0.333 | 0.333 | +0.000 | +0.000 | +0.000 |
| niche_fact | NDCG@10 line | 21 | 0.280 | 0.280 | 0.182 | +0.098 | +0.098 | +0.000 |
| niche_fact | Coverage line | 21 | 0.278 | 0.278 | 0.333 | -0.056 | -0.056 | +0.000 |
| niche_fact | Evidence chars | 21 | 499.143 | 500.000 | 500.000 | +0.000 | -0.857 | +0.857 |
| niche_fact | Chunks kept | 21 | 2.000 | 2.000 | 1.238 | +0.762 | +0.762 | +0.000 |
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
| scope_collection | Chunks kept | 15 | 2.000 | 1.867 | 1.267 | +0.600 | +0.733 | -0.133 |
| self_correct | Coverage@budget_lenient | 20 | 0.200 | 0.300 | 0.342 | -0.042 | -0.142 | +0.100 |
| self_correct | MRR@chunks | 20 | 0.175 | 0.250 | 0.375 | -0.125 | -0.200 | +0.075 |
| self_correct | ChunkHit@1 | 20 | 0.150 | 0.200 | 0.350 | -0.150 | -0.200 | +0.050 |
| self_correct | Precision@1 line | 20 | 0.050 | 0.100 | 0.050 | +0.050 | +0.000 | +0.050 |
| self_correct | Precision@3 line | 20 | 0.083 | 0.142 | 0.083 | +0.058 | +0.000 | +0.058 |
| self_correct | Precision@5 line | 20 | 0.083 | 0.142 | 0.077 | +0.065 | +0.007 | +0.058 |
| self_correct | MRR line | 20 | 0.117 | 0.192 | 0.162 | +0.029 | -0.046 | +0.075 |
| self_correct | Hit@5 line | 20 | 0.200 | 0.300 | 0.350 | -0.050 | -0.150 | +0.100 |
| self_correct | NDCG@10 line | 20 | 0.182 | 0.282 | 0.223 | +0.059 | -0.041 | +0.100 |
| self_correct | Coverage line | 20 | 0.200 | 0.300 | 0.342 | -0.042 | -0.142 | +0.100 |
| self_correct | Evidence chars | 20 | 499.800 | 499.800 | 499.350 | +0.450 | +0.450 | +0.000 |
| self_correct | Chunks kept | 20 | 1.800 | 1.800 | 1.250 | +0.550 | +0.550 | +0.000 |

## budget=1000 (n=77)

Hierarchical dense scoring mode: `full_text`.
Hierarchical retrieval mode: `multi_level_leaf_path_pool`.

Candidate pool path-depth check:
- Gold-hier: n=30761, path_depth_mean=1.697, max=5, hist={'1': 12632, '2': 14904, '3': 3130, '4': 93, '5': 2}
- Pred-hier: n=29868, path_depth_mean=1.669, max=5, hist={'1': 13445, '2': 13018, '3': 3248, '4': 155, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.216 | 0.265 | 0.318 | -0.053 | -0.102 | +0.049 |
| MRR@chunks | 0.246 | 0.286 | 0.398 | -0.113 | -0.153 | +0.040 |
| ChunkHit@1 | 0.208 | 0.247 | 0.364 | -0.117 | -0.156 | +0.039 |
| Precision@1 line | 0.117 | 0.156 | 0.065 | +0.091 | +0.052 | +0.039 |
| Precision@3 line | 0.115 | 0.117 | 0.061 | +0.056 | +0.054 | +0.002 |
| Precision@5 line | 0.107 | 0.111 | 0.068 | +0.043 | +0.039 | +0.005 |
| MRR line | 0.194 | 0.232 | 0.156 | +0.076 | +0.038 | +0.039 |
| Hit@5 line | 0.299 | 0.338 | 0.338 | +0.000 | -0.039 | +0.039 |
| NDCG@10 line | 0.196 | 0.231 | 0.172 | +0.059 | +0.024 | +0.035 |
| Coverage line | 0.216 | 0.265 | 0.318 | -0.053 | -0.102 | +0.049 |
| Evidence chars | 999.974 | 1000.000 | 999.623 | +0.377 | +0.351 | +0.026 |
| Chunks kept | 2.857 | 2.740 | 2.091 | +0.649 | +0.766 | -0.117 |

### Per-type all metrics (budget=1000)

| task_type | Metric | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | Coverage@budget_lenient | 9 | 0.167 | 0.139 | 0.176 | -0.037 | -0.009 | -0.028 |
| cross_section_conflict | MRR@chunks | 9 | 0.278 | 0.333 | 0.444 | -0.111 | -0.167 | +0.056 |
| cross_section_conflict | ChunkHit@1 | 9 | 0.222 | 0.333 | 0.444 | -0.111 | -0.222 | +0.111 |
| cross_section_conflict | Precision@1 line | 9 | 0.222 | 0.333 | 0.222 | +0.111 | +0.000 | +0.111 |
| cross_section_conflict | Precision@3 line | 9 | 0.130 | 0.111 | 0.111 | +0.000 | +0.019 | -0.019 |
| cross_section_conflict | Precision@5 line | 9 | 0.115 | 0.102 | 0.089 | +0.013 | +0.026 | -0.013 |
| cross_section_conflict | MRR line | 9 | 0.259 | 0.333 | 0.281 | +0.052 | -0.022 | +0.074 |
| cross_section_conflict | Hit@5 line | 9 | 0.333 | 0.333 | 0.444 | -0.111 | -0.111 | +0.000 |
| cross_section_conflict | NDCG@10 line | 9 | 0.147 | 0.147 | 0.144 | +0.002 | +0.003 | -0.001 |
| cross_section_conflict | Coverage line | 9 | 0.167 | 0.139 | 0.176 | -0.037 | -0.009 | -0.028 |
| cross_section_conflict | Evidence chars | 9 | 1000.000 | 1000.000 | 1000.000 | +0.000 | +0.000 | +0.000 |
| cross_section_conflict | Chunks kept | 9 | 2.333 | 2.111 | 1.889 | +0.222 | +0.444 | -0.222 |
| multi_hop | Coverage@budget_lenient | 12 | 0.111 | 0.111 | 0.208 | -0.097 | -0.097 | +0.000 |
| multi_hop | MRR@chunks | 12 | 0.250 | 0.250 | 0.417 | -0.167 | -0.167 | +0.000 |
| multi_hop | ChunkHit@1 | 12 | 0.250 | 0.250 | 0.417 | -0.167 | -0.167 | +0.000 |
| multi_hop | Precision@1 line | 12 | 0.167 | 0.083 | 0.083 | +0.000 | +0.083 | -0.083 |
| multi_hop | Precision@3 line | 12 | 0.111 | 0.083 | 0.056 | +0.028 | +0.056 | -0.028 |
| multi_hop | Precision@5 line | 12 | 0.104 | 0.065 | 0.067 | -0.001 | +0.038 | -0.039 |
| multi_hop | MRR line | 12 | 0.208 | 0.167 | 0.159 | +0.008 | +0.049 | -0.042 |
| multi_hop | Hit@5 line | 12 | 0.250 | 0.250 | 0.333 | -0.083 | -0.083 | +0.000 |
| multi_hop | NDCG@10 line | 12 | 0.115 | 0.115 | 0.121 | -0.006 | -0.006 | +0.000 |
| multi_hop | Coverage line | 12 | 0.111 | 0.111 | 0.208 | -0.097 | -0.097 | +0.000 |
| multi_hop | Evidence chars | 12 | 1000.000 | 1000.000 | 1000.000 | +0.000 | +0.000 | +0.000 |
| multi_hop | Chunks kept | 12 | 2.583 | 2.583 | 1.583 | +1.000 | +1.000 | +0.000 |
| niche_fact | Coverage@budget_lenient | 21 | 0.349 | 0.397 | 0.397 | +0.000 | -0.048 | +0.048 |
| niche_fact | MRR@chunks | 21 | 0.337 | 0.385 | 0.421 | -0.036 | -0.083 | +0.048 |
| niche_fact | ChunkHit@1 | 21 | 0.286 | 0.333 | 0.381 | -0.048 | -0.095 | +0.048 |
| niche_fact | Precision@1 line | 21 | 0.095 | 0.190 | 0.048 | +0.143 | +0.048 | +0.095 |
| niche_fact | Precision@3 line | 21 | 0.143 | 0.175 | 0.032 | +0.143 | +0.111 | +0.032 |
| niche_fact | Precision@5 line | 21 | 0.138 | 0.163 | 0.067 | +0.097 | +0.071 | +0.025 |
| niche_fact | MRR line | 21 | 0.242 | 0.313 | 0.132 | +0.182 | +0.110 | +0.071 |
| niche_fact | Hit@5 line | 21 | 0.429 | 0.476 | 0.333 | +0.143 | +0.095 | +0.048 |
| niche_fact | NDCG@10 line | 21 | 0.319 | 0.366 | 0.188 | +0.178 | +0.131 | +0.048 |
| niche_fact | Coverage line | 21 | 0.349 | 0.397 | 0.397 | +0.000 | -0.048 | +0.048 |
| niche_fact | Evidence chars | 21 | 1000.000 | 1000.000 | 999.238 | +0.762 | +0.762 | +0.000 |
| niche_fact | Chunks kept | 21 | 3.048 | 3.095 | 2.048 | +1.048 | +1.000 | +0.048 |
| scope_collection | Coverage@budget_lenient | 15 | 0.067 | 0.133 | 0.250 | -0.117 | -0.183 | +0.067 |
| scope_collection | MRR@chunks | 15 | 0.133 | 0.167 | 0.289 | -0.122 | -0.156 | +0.033 |
| scope_collection | ChunkHit@1 | 15 | 0.133 | 0.133 | 0.267 | -0.133 | -0.133 | +0.000 |
| scope_collection | Precision@1 line | 15 | 0.133 | 0.133 | 0.000 | +0.133 | +0.133 | +0.000 |
| scope_collection | Precision@3 line | 15 | 0.067 | 0.067 | 0.044 | +0.022 | +0.022 | +0.000 |
| scope_collection | Precision@5 line | 15 | 0.061 | 0.074 | 0.057 | +0.018 | +0.004 | +0.013 |
| scope_collection | MRR line | 15 | 0.133 | 0.147 | 0.093 | +0.054 | +0.041 | +0.013 |
| scope_collection | Hit@5 line | 15 | 0.133 | 0.200 | 0.267 | -0.067 | -0.133 | +0.067 |
| scope_collection | NDCG@10 line | 15 | 0.076 | 0.105 | 0.129 | -0.024 | -0.053 | +0.029 |
| scope_collection | Coverage line | 15 | 0.067 | 0.133 | 0.250 | -0.117 | -0.183 | +0.067 |
| scope_collection | Evidence chars | 15 | 1000.000 | 1000.000 | 1000.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | Chunks kept | 15 | 3.000 | 2.400 | 2.333 | +0.067 | +0.667 | -0.600 |
| self_correct | Coverage@budget_lenient | 20 | 0.275 | 0.375 | 0.417 | -0.042 | -0.142 | +0.100 |
| self_correct | MRR@chunks | 20 | 0.217 | 0.271 | 0.425 | -0.154 | -0.208 | +0.054 |
| self_correct | ChunkHit@1 | 20 | 0.150 | 0.200 | 0.350 | -0.150 | -0.200 | +0.050 |
| self_correct | Precision@1 line | 20 | 0.050 | 0.100 | 0.050 | +0.050 | +0.000 | +0.050 |
| self_correct | Precision@3 line | 20 | 0.117 | 0.117 | 0.083 | +0.033 | +0.033 | +0.000 |
| self_correct | Precision@5 line | 20 | 0.106 | 0.116 | 0.070 | +0.046 | +0.036 | +0.010 |
| self_correct | MRR line | 20 | 0.150 | 0.205 | 0.171 | +0.034 | -0.021 | +0.055 |
| self_correct | Hit@5 line | 20 | 0.300 | 0.350 | 0.350 | +0.000 | -0.050 | +0.050 |
| self_correct | NDCG@10 line | 20 | 0.229 | 0.292 | 0.230 | +0.062 | -0.001 | +0.063 |
| self_correct | Coverage line | 20 | 0.275 | 0.375 | 0.417 | -0.042 | -0.142 | +0.100 |
| self_correct | Evidence chars | 20 | 999.900 | 1000.000 | 999.350 | +0.650 | +0.550 | +0.100 |
| self_correct | Chunks kept | 20 | 2.950 | 3.000 | 2.350 | +0.650 | +0.600 | +0.050 |

