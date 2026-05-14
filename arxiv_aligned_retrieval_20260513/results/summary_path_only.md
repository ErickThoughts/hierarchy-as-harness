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

- budget=300: 主指标 Coverage@budget_lenient 最好的是 Pred-hier (0.132)；Pred-Flat=+0.019，Pred-Gold=+0.013；题级 Pred>Gold / Gold>Pred / Tie = 2/1/74。
- budget=500: 主指标 Coverage@budget_lenient 最好的是 Flat-react (0.246)；Pred-Flat=-0.052，Pred-Gold=+0.029；题级 Pred>Gold / Gold>Pred / Tie = 4/1/72。
- budget=1000: 主指标 Coverage@budget_lenient 最好的是 Flat-react (0.318)；Pred-Flat=-0.092，Pred-Gold=+0.019；题级 Pred>Gold / Gold>Pred / Tie = 3/2/72。
- Pred-hier 相对 Flat-react 的收益不稳定：Pred 更好的 budget=300；Flat 更好的 budget=500, 1000；打平 budget=-。
- Pred-hier 平均不低于 Gold-hier：Pred 更好的 budget=300, 500, 1000；打平 budget=-。差异主要来自少数题的 chunk 边界/路径文本变化。

按题型看主指标 Coverage@budget_lenient 的 Pred-Flat：

| Budget | Pred-hier 优于 Flat-react | 打平 | Flat-react 优于 Pred-hier |
| ---: | --- | --- | --- |
| 300 | multi_hop, niche_fact | - | cross_section_conflict, scope_collection, self_correct |
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

Hierarchical dense scoring mode: `path_only`.
Hierarchical retrieval mode: `multi_level_leaf_path_pool`.

Candidate pool path-depth check:
- Gold-hier: n=30761, path_depth_mean=1.697, max=5, hist={'1': 12632, '2': 14904, '3': 3130, '4': 93, '5': 2}
- Pred-hier: n=29868, path_depth_mean=1.669, max=5, hist={'1': 13445, '2': 13018, '3': 3248, '4': 155, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.119 | 0.132 | 0.113 | +0.019 | +0.006 | +0.013 |
| MRR@chunks | 0.169 | 0.182 | 0.195 | -0.013 | -0.026 | +0.013 |
| ChunkHit@1 | 0.169 | 0.182 | 0.195 | -0.013 | -0.026 | +0.013 |
| Precision@1 line | 0.130 | 0.156 | 0.065 | +0.091 | +0.065 | +0.026 |
| Precision@3 line | 0.130 | 0.132 | 0.043 | +0.089 | +0.087 | +0.002 |
| Precision@5 line | 0.130 | 0.132 | 0.045 | +0.087 | +0.085 | +0.002 |
| MRR line | 0.149 | 0.169 | 0.106 | +0.062 | +0.043 | +0.019 |
| Hit@5 line | 0.169 | 0.182 | 0.195 | -0.013 | -0.026 | +0.013 |
| NDCG@10 line | 0.122 | 0.135 | 0.092 | +0.043 | +0.030 | +0.013 |
| Coverage line | 0.119 | 0.132 | 0.113 | +0.019 | +0.006 | +0.013 |
| Evidence chars | 299.948 | 300.000 | 299.351 | +0.649 | +0.597 | +0.052 |
| Chunks kept | 1.351 | 1.364 | 1.039 | +0.325 | +0.312 | +0.013 |

### Per-type all metrics (budget=300)

| task_type | Metric | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | Coverage@budget_lenient | 9 | 0.111 | 0.111 | 0.176 | -0.065 | -0.065 | +0.000 |
| cross_section_conflict | MRR@chunks | 9 | 0.222 | 0.222 | 0.444 | -0.222 | -0.222 | +0.000 |
| cross_section_conflict | ChunkHit@1 | 9 | 0.222 | 0.222 | 0.444 | -0.222 | -0.222 | +0.000 |
| cross_section_conflict | Precision@1 line | 9 | 0.222 | 0.222 | 0.222 | +0.000 | +0.000 | +0.000 |
| cross_section_conflict | Precision@3 line | 9 | 0.167 | 0.093 | 0.111 | -0.019 | +0.056 | -0.074 |
| cross_section_conflict | Precision@5 line | 9 | 0.167 | 0.093 | 0.104 | -0.011 | +0.063 | -0.074 |
| cross_section_conflict | MRR line | 9 | 0.222 | 0.222 | 0.281 | -0.059 | -0.059 | +0.000 |
| cross_section_conflict | Hit@5 line | 9 | 0.222 | 0.222 | 0.444 | -0.222 | -0.222 | +0.000 |
| cross_section_conflict | NDCG@10 line | 9 | 0.111 | 0.111 | 0.144 | -0.033 | -0.033 | +0.000 |
| cross_section_conflict | Coverage line | 9 | 0.111 | 0.111 | 0.176 | -0.065 | -0.065 | +0.000 |
| cross_section_conflict | Evidence chars | 9 | 299.556 | 300.000 | 299.222 | +0.778 | +0.333 | +0.444 |
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
| niche_fact | Coverage@budget_lenient | 21 | 0.206 | 0.206 | 0.071 | +0.135 | +0.135 | +0.000 |
| niche_fact | MRR@chunks | 21 | 0.238 | 0.238 | 0.095 | +0.143 | +0.143 | +0.000 |
| niche_fact | ChunkHit@1 | 21 | 0.238 | 0.238 | 0.095 | +0.143 | +0.143 | +0.000 |
| niche_fact | Precision@1 line | 21 | 0.095 | 0.190 | 0.048 | +0.143 | +0.048 | +0.095 |
| niche_fact | Precision@3 line | 21 | 0.167 | 0.183 | 0.016 | +0.167 | +0.151 | +0.016 |
| niche_fact | Precision@5 line | 21 | 0.167 | 0.183 | 0.021 | +0.161 | +0.145 | +0.016 |
| niche_fact | MRR line | 21 | 0.167 | 0.214 | 0.060 | +0.155 | +0.107 | +0.048 |
| niche_fact | Hit@5 line | 21 | 0.238 | 0.238 | 0.095 | +0.143 | +0.143 | +0.000 |
| niche_fact | NDCG@10 line | 21 | 0.209 | 0.209 | 0.060 | +0.149 | +0.149 | +0.000 |
| niche_fact | Coverage line | 21 | 0.206 | 0.206 | 0.071 | +0.135 | +0.135 | +0.000 |
| niche_fact | Evidence chars | 21 | 300.000 | 300.000 | 299.000 | +1.000 | +1.000 | +0.000 |
| niche_fact | Chunks kept | 21 | 1.381 | 1.476 | 1.048 | +0.429 | +0.333 | +0.095 |
| scope_collection | Coverage@budget_lenient | 15 | 0.067 | 0.067 | 0.083 | -0.017 | -0.017 | +0.000 |
| scope_collection | MRR@chunks | 15 | 0.133 | 0.133 | 0.200 | -0.067 | -0.067 | +0.000 |
| scope_collection | ChunkHit@1 | 15 | 0.133 | 0.133 | 0.200 | -0.067 | -0.067 | +0.000 |
| scope_collection | Precision@1 line | 15 | 0.133 | 0.133 | 0.000 | +0.133 | +0.133 | +0.000 |
| scope_collection | Precision@3 line | 15 | 0.133 | 0.133 | 0.022 | +0.111 | +0.111 | +0.000 |
| scope_collection | Precision@5 line | 15 | 0.133 | 0.133 | 0.040 | +0.093 | +0.093 | +0.000 |
| scope_collection | MRR line | 15 | 0.133 | 0.133 | 0.056 | +0.078 | +0.078 | +0.000 |
| scope_collection | Hit@5 line | 15 | 0.133 | 0.133 | 0.200 | -0.067 | -0.067 | +0.000 |
| scope_collection | NDCG@10 line | 15 | 0.076 | 0.076 | 0.048 | +0.028 | +0.028 | +0.000 |
| scope_collection | Coverage line | 15 | 0.067 | 0.067 | 0.083 | -0.017 | -0.017 | +0.000 |
| scope_collection | Evidence chars | 15 | 300.000 | 300.000 | 298.733 | +1.267 | +1.267 | +0.000 |
| scope_collection | Chunks kept | 15 | 1.333 | 1.333 | 1.000 | +0.333 | +0.333 | +0.000 |
| self_correct | Coverage@budget_lenient | 20 | 0.100 | 0.150 | 0.192 | -0.042 | -0.092 | +0.050 |
| self_correct | MRR@chunks | 20 | 0.100 | 0.150 | 0.250 | -0.100 | -0.150 | +0.050 |
| self_correct | ChunkHit@1 | 20 | 0.100 | 0.150 | 0.250 | -0.100 | -0.150 | +0.050 |
| self_correct | Precision@1 line | 20 | 0.100 | 0.150 | 0.050 | +0.100 | +0.050 | +0.050 |
| self_correct | Precision@3 line | 20 | 0.050 | 0.100 | 0.067 | +0.033 | -0.017 | +0.050 |
| self_correct | Precision@5 line | 20 | 0.050 | 0.100 | 0.064 | +0.036 | -0.014 | +0.050 |
| self_correct | MRR line | 20 | 0.100 | 0.150 | 0.129 | +0.021 | -0.029 | +0.050 |
| self_correct | Hit@5 line | 20 | 0.100 | 0.150 | 0.250 | -0.100 | -0.150 | +0.050 |
| self_correct | NDCG@10 line | 20 | 0.100 | 0.150 | 0.166 | -0.016 | -0.066 | +0.050 |
| self_correct | Coverage line | 20 | 0.100 | 0.150 | 0.192 | -0.042 | -0.092 | +0.050 |
| self_correct | Evidence chars | 20 | 300.000 | 300.000 | 299.850 | +0.150 | +0.150 | +0.000 |
| self_correct | Chunks kept | 20 | 1.500 | 1.400 | 1.050 | +0.350 | +0.450 | -0.100 |

## budget=500 (n=77)

Hierarchical dense scoring mode: `path_only`.
Hierarchical retrieval mode: `multi_level_leaf_path_pool`.

Candidate pool path-depth check:
- Gold-hier: n=30761, path_depth_mean=1.697, max=5, hist={'1': 12632, '2': 14904, '3': 3130, '4': 93, '5': 2}
- Pred-hier: n=29868, path_depth_mean=1.669, max=5, hist={'1': 13445, '2': 13018, '3': 3248, '4': 155, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.165 | 0.194 | 0.246 | -0.052 | -0.081 | +0.029 |
| MRR@chunks | 0.221 | 0.240 | 0.325 | -0.084 | -0.104 | +0.019 |
| ChunkHit@1 | 0.208 | 0.208 | 0.312 | -0.104 | -0.104 | +0.000 |
| Precision@1 line | 0.130 | 0.156 | 0.065 | +0.091 | +0.065 | +0.026 |
| Precision@3 line | 0.128 | 0.139 | 0.063 | +0.076 | +0.065 | +0.011 |
| Precision@5 line | 0.128 | 0.139 | 0.070 | +0.069 | +0.058 | +0.011 |
| MRR line | 0.182 | 0.207 | 0.143 | +0.064 | +0.039 | +0.025 |
| Hit@5 line | 0.234 | 0.260 | 0.312 | -0.052 | -0.078 | +0.026 |
| NDCG@10 line | 0.168 | 0.187 | 0.159 | +0.029 | +0.009 | +0.020 |
| Coverage line | 0.165 | 0.194 | 0.246 | -0.052 | -0.081 | +0.029 |
| Evidence chars | 500.000 | 499.896 | 499.195 | +0.701 | +0.805 | -0.104 |
| Chunks kept | 1.818 | 1.805 | 1.273 | +0.532 | +0.545 | -0.013 |

### Per-type all metrics (budget=500)

| task_type | Metric | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | Coverage@budget_lenient | 9 | 0.111 | 0.139 | 0.176 | -0.037 | -0.065 | +0.028 |
| cross_section_conflict | MRR@chunks | 9 | 0.222 | 0.278 | 0.444 | -0.167 | -0.222 | +0.056 |
| cross_section_conflict | ChunkHit@1 | 9 | 0.222 | 0.222 | 0.444 | -0.222 | -0.222 | +0.000 |
| cross_section_conflict | Precision@1 line | 9 | 0.222 | 0.222 | 0.222 | +0.000 | +0.000 | +0.000 |
| cross_section_conflict | Precision@3 line | 9 | 0.111 | 0.111 | 0.111 | +0.000 | +0.000 | +0.000 |
| cross_section_conflict | Precision@5 line | 9 | 0.111 | 0.111 | 0.094 | +0.017 | +0.017 | +0.000 |
| cross_section_conflict | MRR line | 9 | 0.222 | 0.259 | 0.281 | -0.022 | -0.059 | +0.037 |
| cross_section_conflict | Hit@5 line | 9 | 0.222 | 0.333 | 0.444 | -0.111 | -0.222 | +0.111 |
| cross_section_conflict | NDCG@10 line | 9 | 0.111 | 0.134 | 0.144 | -0.011 | -0.033 | +0.022 |
| cross_section_conflict | Coverage line | 9 | 0.111 | 0.139 | 0.176 | -0.037 | -0.065 | +0.028 |
| cross_section_conflict | Evidence chars | 9 | 500.000 | 500.000 | 500.000 | +0.000 | +0.000 | +0.000 |
| cross_section_conflict | Chunks kept | 9 | 1.556 | 1.556 | 1.556 | +0.000 | +0.000 | +0.000 |
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
| multi_hop | Evidence chars | 12 | 500.000 | 499.333 | 498.250 | +1.083 | +1.750 | -0.667 |
| multi_hop | Chunks kept | 12 | 1.500 | 1.500 | 1.167 | +0.333 | +0.333 | +0.000 |
| niche_fact | Coverage@budget_lenient | 21 | 0.278 | 0.230 | 0.333 | -0.103 | -0.056 | -0.048 |
| niche_fact | MRR@chunks | 21 | 0.310 | 0.262 | 0.357 | -0.095 | -0.048 | -0.048 |
| niche_fact | ChunkHit@1 | 21 | 0.286 | 0.238 | 0.333 | -0.095 | -0.048 | -0.048 |
| niche_fact | Precision@1 line | 21 | 0.095 | 0.190 | 0.048 | +0.143 | +0.048 | +0.095 |
| niche_fact | Precision@3 line | 21 | 0.167 | 0.167 | 0.032 | +0.135 | +0.135 | +0.000 |
| niche_fact | Precision@5 line | 21 | 0.167 | 0.167 | 0.069 | +0.098 | +0.098 | +0.000 |
| niche_fact | MRR line | 21 | 0.214 | 0.238 | 0.123 | +0.115 | +0.091 | +0.024 |
| niche_fact | Hit@5 line | 21 | 0.333 | 0.286 | 0.333 | -0.048 | +0.000 | -0.048 |
| niche_fact | NDCG@10 line | 21 | 0.280 | 0.232 | 0.182 | +0.050 | +0.098 | -0.048 |
| niche_fact | Coverage line | 21 | 0.278 | 0.230 | 0.333 | -0.103 | -0.056 | -0.048 |
| niche_fact | Evidence chars | 21 | 500.000 | 500.000 | 500.000 | +0.000 | +0.000 | +0.000 |
| niche_fact | Chunks kept | 21 | 2.048 | 2.048 | 1.238 | +0.810 | +0.810 | +0.000 |
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
| scope_collection | Chunks kept | 15 | 1.867 | 1.867 | 1.267 | +0.600 | +0.600 | +0.000 |
| self_correct | Coverage@budget_lenient | 20 | 0.175 | 0.325 | 0.342 | -0.017 | -0.167 | +0.150 |
| self_correct | MRR@chunks | 20 | 0.175 | 0.275 | 0.375 | -0.100 | -0.200 | +0.100 |
| self_correct | ChunkHit@1 | 20 | 0.150 | 0.200 | 0.350 | -0.150 | -0.200 | +0.050 |
| self_correct | Precision@1 line | 20 | 0.100 | 0.150 | 0.050 | +0.100 | +0.050 | +0.050 |
| self_correct | Precision@3 line | 20 | 0.092 | 0.142 | 0.083 | +0.058 | +0.008 | +0.050 |
| self_correct | Precision@5 line | 20 | 0.092 | 0.142 | 0.077 | +0.065 | +0.015 | +0.050 |
| self_correct | MRR line | 20 | 0.150 | 0.231 | 0.162 | +0.069 | -0.012 | +0.081 |
| self_correct | Hit@5 line | 20 | 0.200 | 0.300 | 0.350 | -0.050 | -0.150 | +0.100 |
| self_correct | NDCG@10 line | 20 | 0.175 | 0.292 | 0.223 | +0.069 | -0.048 | +0.117 |
| self_correct | Coverage line | 20 | 0.175 | 0.325 | 0.342 | -0.017 | -0.167 | +0.150 |
| self_correct | Evidence chars | 20 | 500.000 | 500.000 | 499.350 | +0.650 | +0.650 | +0.000 |
| self_correct | Chunks kept | 20 | 1.850 | 1.800 | 1.250 | +0.550 | +0.600 | -0.050 |

## budget=1000 (n=77)

Hierarchical dense scoring mode: `path_only`.
Hierarchical retrieval mode: `multi_level_leaf_path_pool`.

Candidate pool path-depth check:
- Gold-hier: n=30761, path_depth_mean=1.697, max=5, hist={'1': 12632, '2': 14904, '3': 3130, '4': 93, '5': 2}
- Pred-hier: n=29868, path_depth_mean=1.669, max=5, hist={'1': 13445, '2': 13018, '3': 3248, '4': 155, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.207 | 0.226 | 0.318 | -0.092 | -0.111 | +0.019 |
| MRR@chunks | 0.247 | 0.260 | 0.398 | -0.138 | -0.151 | +0.013 |
| ChunkHit@1 | 0.208 | 0.221 | 0.364 | -0.143 | -0.156 | +0.013 |
| Precision@1 line | 0.130 | 0.156 | 0.065 | +0.091 | +0.065 | +0.026 |
| Precision@3 line | 0.117 | 0.113 | 0.061 | +0.052 | +0.056 | -0.004 |
| Precision@5 line | 0.109 | 0.104 | 0.068 | +0.036 | +0.041 | -0.005 |
| MRR line | 0.202 | 0.221 | 0.156 | +0.065 | +0.046 | +0.019 |
| Hit@5 line | 0.299 | 0.299 | 0.338 | -0.039 | -0.039 | +0.000 |
| NDCG@10 line | 0.192 | 0.210 | 0.172 | +0.038 | +0.020 | +0.018 |
| Coverage line | 0.207 | 0.226 | 0.318 | -0.092 | -0.111 | +0.019 |
| Evidence chars | 999.870 | 999.597 | 999.623 | -0.026 | +0.247 | -0.273 |
| Chunks kept | 2.831 | 2.727 | 2.091 | +0.636 | +0.740 | -0.104 |

### Per-type all metrics (budget=1000)

| task_type | Metric | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | Coverage@budget_lenient | 9 | 0.139 | 0.139 | 0.176 | -0.037 | -0.037 | +0.000 |
| cross_section_conflict | MRR@chunks | 9 | 0.278 | 0.278 | 0.444 | -0.167 | -0.167 | +0.000 |
| cross_section_conflict | ChunkHit@1 | 9 | 0.222 | 0.222 | 0.444 | -0.222 | -0.222 | +0.000 |
| cross_section_conflict | Precision@1 line | 9 | 0.222 | 0.222 | 0.222 | +0.000 | +0.000 | +0.000 |
| cross_section_conflict | Precision@3 line | 9 | 0.130 | 0.111 | 0.111 | +0.000 | +0.019 | -0.019 |
| cross_section_conflict | Precision@5 line | 9 | 0.115 | 0.102 | 0.089 | +0.013 | +0.026 | -0.013 |
| cross_section_conflict | MRR line | 9 | 0.259 | 0.259 | 0.281 | -0.022 | -0.022 | +0.000 |
| cross_section_conflict | Hit@5 line | 9 | 0.333 | 0.333 | 0.444 | -0.111 | -0.111 | +0.000 |
| cross_section_conflict | NDCG@10 line | 9 | 0.134 | 0.134 | 0.144 | -0.011 | -0.011 | +0.000 |
| cross_section_conflict | Coverage line | 9 | 0.139 | 0.139 | 0.176 | -0.037 | -0.037 | +0.000 |
| cross_section_conflict | Evidence chars | 9 | 1000.000 | 1000.000 | 1000.000 | +0.000 | +0.000 | +0.000 |
| cross_section_conflict | Chunks kept | 9 | 2.333 | 2.222 | 1.889 | +0.333 | +0.444 | -0.111 |
| multi_hop | Coverage@budget_lenient | 12 | 0.111 | 0.111 | 0.208 | -0.097 | -0.097 | +0.000 |
| multi_hop | MRR@chunks | 12 | 0.250 | 0.250 | 0.417 | -0.167 | -0.167 | +0.000 |
| multi_hop | ChunkHit@1 | 12 | 0.250 | 0.250 | 0.417 | -0.167 | -0.167 | +0.000 |
| multi_hop | Precision@1 line | 12 | 0.167 | 0.083 | 0.083 | +0.000 | +0.083 | -0.083 |
| multi_hop | Precision@3 line | 12 | 0.111 | 0.083 | 0.056 | +0.028 | +0.056 | -0.028 |
| multi_hop | Precision@5 line | 12 | 0.104 | 0.072 | 0.067 | +0.006 | +0.038 | -0.032 |
| multi_hop | MRR line | 12 | 0.208 | 0.167 | 0.159 | +0.008 | +0.049 | -0.042 |
| multi_hop | Hit@5 line | 12 | 0.250 | 0.250 | 0.333 | -0.083 | -0.083 | +0.000 |
| multi_hop | NDCG@10 line | 12 | 0.115 | 0.115 | 0.121 | -0.006 | -0.006 | +0.000 |
| multi_hop | Coverage line | 12 | 0.111 | 0.111 | 0.208 | -0.097 | -0.097 | +0.000 |
| multi_hop | Evidence chars | 12 | 1000.000 | 1000.000 | 1000.000 | +0.000 | +0.000 | +0.000 |
| multi_hop | Chunks kept | 12 | 2.583 | 2.583 | 1.583 | +1.000 | +1.000 | +0.000 |
| niche_fact | Coverage@budget_lenient | 21 | 0.349 | 0.349 | 0.397 | -0.048 | -0.048 | +0.000 |
| niche_fact | MRR@chunks | 21 | 0.335 | 0.335 | 0.421 | -0.086 | -0.086 | +0.000 |
| niche_fact | ChunkHit@1 | 21 | 0.286 | 0.286 | 0.381 | -0.095 | -0.095 | +0.000 |
| niche_fact | Precision@1 line | 21 | 0.095 | 0.190 | 0.048 | +0.143 | +0.048 | +0.095 |
| niche_fact | Precision@3 line | 21 | 0.151 | 0.159 | 0.032 | +0.127 | +0.119 | +0.008 |
| niche_fact | Precision@5 line | 21 | 0.144 | 0.152 | 0.067 | +0.085 | +0.077 | +0.008 |
| niche_fact | MRR line | 21 | 0.240 | 0.287 | 0.132 | +0.156 | +0.108 | +0.048 |
| niche_fact | Hit@5 line | 21 | 0.429 | 0.429 | 0.333 | +0.095 | +0.095 | +0.000 |
| niche_fact | NDCG@10 line | 21 | 0.316 | 0.316 | 0.188 | +0.127 | +0.127 | +0.000 |
| niche_fact | Coverage line | 21 | 0.349 | 0.349 | 0.397 | -0.048 | -0.048 | +0.000 |
| niche_fact | Evidence chars | 21 | 999.619 | 999.095 | 999.238 | -0.143 | +0.381 | -0.524 |
| niche_fact | Chunks kept | 21 | 3.048 | 2.952 | 2.048 | +0.905 | +1.000 | -0.095 |
| scope_collection | Coverage@budget_lenient | 15 | 0.067 | 0.067 | 0.250 | -0.183 | -0.183 | +0.000 |
| scope_collection | MRR@chunks | 15 | 0.133 | 0.133 | 0.289 | -0.156 | -0.156 | +0.000 |
| scope_collection | ChunkHit@1 | 15 | 0.133 | 0.133 | 0.267 | -0.133 | -0.133 | +0.000 |
| scope_collection | Precision@1 line | 15 | 0.133 | 0.133 | 0.000 | +0.133 | +0.133 | +0.000 |
| scope_collection | Precision@3 line | 15 | 0.067 | 0.067 | 0.044 | +0.022 | +0.022 | +0.000 |
| scope_collection | Precision@5 line | 15 | 0.061 | 0.061 | 0.057 | +0.004 | +0.004 | +0.000 |
| scope_collection | MRR line | 15 | 0.133 | 0.133 | 0.093 | +0.041 | +0.041 | +0.000 |
| scope_collection | Hit@5 line | 15 | 0.133 | 0.133 | 0.267 | -0.133 | -0.133 | +0.000 |
| scope_collection | NDCG@10 line | 15 | 0.076 | 0.076 | 0.129 | -0.053 | -0.053 | +0.000 |
| scope_collection | Coverage line | 15 | 0.067 | 0.067 | 0.250 | -0.183 | -0.183 | +0.000 |
| scope_collection | Evidence chars | 15 | 1000.000 | 1000.000 | 1000.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | Chunks kept | 15 | 3.000 | 2.733 | 2.333 | +0.400 | +0.667 | -0.267 |
| self_correct | Coverage@budget_lenient | 20 | 0.250 | 0.325 | 0.417 | -0.092 | -0.167 | +0.075 |
| self_correct | MRR@chunks | 20 | 0.225 | 0.275 | 0.425 | -0.150 | -0.200 | +0.050 |
| self_correct | ChunkHit@1 | 20 | 0.150 | 0.200 | 0.350 | -0.150 | -0.200 | +0.050 |
| self_correct | Precision@1 line | 20 | 0.100 | 0.150 | 0.050 | +0.100 | +0.050 | +0.050 |
| self_correct | Precision@3 line | 20 | 0.117 | 0.117 | 0.083 | +0.033 | +0.033 | +0.000 |
| self_correct | Precision@5 line | 20 | 0.110 | 0.106 | 0.070 | +0.036 | +0.040 | -0.004 |
| self_correct | MRR line | 20 | 0.183 | 0.231 | 0.171 | +0.061 | +0.013 | +0.048 |
| self_correct | Hit@5 line | 20 | 0.300 | 0.300 | 0.350 | -0.050 | -0.050 | +0.000 |
| self_correct | NDCG@10 line | 20 | 0.222 | 0.292 | 0.230 | +0.062 | -0.008 | +0.069 |
| self_correct | Coverage line | 20 | 0.250 | 0.325 | 0.417 | -0.092 | -0.167 | +0.075 |
| self_correct | Evidence chars | 20 | 999.900 | 999.400 | 999.350 | +0.050 | +0.550 | -0.500 |
| self_correct | Chunks kept | 20 | 2.850 | 2.800 | 2.350 | +0.450 | +0.500 | -0.050 |

