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

- budget=300: 主指标 Coverage@budget_lenient 最好的是 Pred-hier (0.141)；Pred-Flat=+0.028，Pred-Gold=+0.026；题级 Pred>Gold / Gold>Pred / Tie = 3/2/72。
- budget=500: 主指标 Coverage@budget_lenient 最好的是 Flat-react (0.246)；Pred-Flat=-0.019，Pred-Gold=+0.045；题级 Pred>Gold / Gold>Pred / Tie = 5/2/70。
- budget=1000: 主指标 Coverage@budget_lenient 最好的是 Pred-hier (0.324)；Pred-Flat=+0.005，Pred-Gold=+0.084；题级 Pred>Gold / Gold>Pred / Tie = 10/3/64。
- Pred-hier 相对 Flat-react 的收益不稳定：Pred 更好的 budget=300, 1000；Flat 更好的 budget=500；打平 budget=-。
- Pred-hier 平均不低于 Gold-hier：Pred 更好的 budget=300, 500, 1000；打平 budget=-。差异主要来自少数题的 chunk 边界/路径文本变化。

按题型看主指标 Coverage@budget_lenient 的 Pred-Flat：

| Budget | Pred-hier 优于 Flat-react | 打平 | Flat-react 优于 Pred-hier |
| ---: | --- | --- | --- |
| 300 | multi_hop, niche_fact, scope_collection | - | cross_section_conflict, self_correct |
| 500 | multi_hop, self_correct | scope_collection | cross_section_conflict, niche_fact |
| 1000 | niche_fact, self_correct | - | cross_section_conflict, multi_hop, scope_collection |

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
Hierarchical retrieval mode: `length_normalized`.
Length-normalized body window chars: `220`.

Candidate pool path-depth check:
- Gold-hier: n=30761, path_depth_mean=1.697, max=5, hist={'1': 12632, '2': 14904, '3': 3130, '4': 93, '5': 2}
- Pred-hier: n=30191, path_depth_mean=1.664, max=5, hist={'1': 13728, '2': 13052, '3': 3254, '4': 155, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.115 | 0.141 | 0.113 | +0.028 | +0.002 | +0.026 |
| MRR@chunks | 0.169 | 0.182 | 0.195 | -0.013 | -0.026 | +0.013 |
| ChunkHit@1 | 0.169 | 0.182 | 0.195 | -0.013 | -0.026 | +0.013 |
| Precision@1 line | 0.130 | 0.104 | 0.065 | +0.039 | +0.065 | -0.026 |
| Precision@3 line | 0.136 | 0.126 | 0.043 | +0.082 | +0.093 | -0.011 |
| Precision@5 line | 0.136 | 0.124 | 0.045 | +0.079 | +0.091 | -0.013 |
| MRR line | 0.149 | 0.143 | 0.106 | +0.036 | +0.043 | -0.006 |
| Hit@5 line | 0.169 | 0.182 | 0.195 | -0.013 | -0.026 | +0.013 |
| NDCG@10 line | 0.117 | 0.143 | 0.092 | +0.051 | +0.025 | +0.026 |
| Coverage line | 0.115 | 0.141 | 0.113 | +0.028 | +0.002 | +0.026 |
| Evidence chars | 299.857 | 300.000 | 299.351 | +0.649 | +0.506 | +0.143 |
| Chunks kept | 1.416 | 1.403 | 1.039 | +0.364 | +0.377 | -0.013 |

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
| multi_hop | Chunks kept | 12 | 1.333 | 1.417 | 1.000 | +0.417 | +0.333 | +0.083 |
| niche_fact | Coverage@budget_lenient | 21 | 0.143 | 0.238 | 0.071 | +0.167 | +0.071 | +0.095 |
| niche_fact | MRR@chunks | 21 | 0.143 | 0.238 | 0.095 | +0.143 | +0.048 | +0.095 |
| niche_fact | ChunkHit@1 | 21 | 0.143 | 0.238 | 0.095 | +0.143 | +0.048 | +0.095 |
| niche_fact | Precision@1 line | 21 | 0.048 | 0.143 | 0.048 | +0.095 | +0.000 | +0.095 |
| niche_fact | Precision@3 line | 21 | 0.095 | 0.151 | 0.016 | +0.135 | +0.079 | +0.056 |
| niche_fact | Precision@5 line | 21 | 0.095 | 0.144 | 0.021 | +0.123 | +0.074 | +0.049 |
| niche_fact | MRR line | 21 | 0.095 | 0.190 | 0.060 | +0.131 | +0.036 | +0.095 |
| niche_fact | Hit@5 line | 21 | 0.143 | 0.238 | 0.095 | +0.143 | +0.048 | +0.095 |
| niche_fact | NDCG@10 line | 21 | 0.143 | 0.238 | 0.060 | +0.179 | +0.083 | +0.095 |
| niche_fact | Coverage line | 21 | 0.143 | 0.238 | 0.071 | +0.167 | +0.071 | +0.095 |
| niche_fact | Evidence chars | 21 | 300.000 | 300.000 | 299.000 | +1.000 | +1.000 | +0.000 |
| niche_fact | Chunks kept | 21 | 1.667 | 1.571 | 1.048 | +0.524 | +0.619 | -0.095 |
| scope_collection | Coverage@budget_lenient | 15 | 0.050 | 0.117 | 0.083 | +0.033 | -0.033 | +0.067 |
| scope_collection | MRR@chunks | 15 | 0.133 | 0.200 | 0.200 | +0.000 | -0.067 | +0.067 |
| scope_collection | ChunkHit@1 | 15 | 0.133 | 0.200 | 0.200 | +0.000 | -0.067 | +0.067 |
| scope_collection | Precision@1 line | 15 | 0.133 | 0.067 | 0.000 | +0.067 | +0.133 | -0.067 |
| scope_collection | Precision@3 line | 15 | 0.133 | 0.133 | 0.022 | +0.111 | +0.111 | +0.000 |
| scope_collection | Precision@5 line | 15 | 0.133 | 0.133 | 0.040 | +0.093 | +0.093 | +0.000 |
| scope_collection | MRR line | 15 | 0.133 | 0.133 | 0.056 | +0.078 | +0.078 | +0.000 |
| scope_collection | Hit@5 line | 15 | 0.133 | 0.200 | 0.200 | +0.000 | -0.067 | +0.067 |
| scope_collection | NDCG@10 line | 15 | 0.055 | 0.121 | 0.048 | +0.073 | +0.006 | +0.067 |
| scope_collection | Coverage line | 15 | 0.050 | 0.117 | 0.083 | +0.033 | -0.033 | +0.067 |
| scope_collection | Evidence chars | 15 | 300.000 | 300.000 | 298.733 | +1.267 | +1.267 | +0.000 |
| scope_collection | Chunks kept | 15 | 1.333 | 1.333 | 1.000 | +0.333 | +0.333 | +0.000 |
| self_correct | Coverage@budget_lenient | 20 | 0.150 | 0.150 | 0.192 | -0.042 | -0.042 | +0.000 |
| self_correct | MRR@chunks | 20 | 0.150 | 0.150 | 0.250 | -0.100 | -0.100 | +0.000 |
| self_correct | ChunkHit@1 | 20 | 0.150 | 0.150 | 0.250 | -0.100 | -0.100 | +0.000 |
| self_correct | Precision@1 line | 20 | 0.100 | 0.100 | 0.050 | +0.050 | +0.050 | +0.000 |
| self_correct | Precision@3 line | 20 | 0.100 | 0.100 | 0.067 | +0.033 | +0.033 | +0.000 |
| self_correct | Precision@5 line | 20 | 0.100 | 0.100 | 0.064 | +0.036 | +0.036 | +0.000 |
| self_correct | MRR line | 20 | 0.125 | 0.125 | 0.129 | -0.004 | -0.004 | +0.000 |
| self_correct | Hit@5 line | 20 | 0.150 | 0.150 | 0.250 | -0.100 | -0.100 | +0.000 |
| self_correct | NDCG@10 line | 20 | 0.150 | 0.150 | 0.166 | -0.016 | -0.016 | +0.000 |
| self_correct | Coverage line | 20 | 0.150 | 0.150 | 0.192 | -0.042 | -0.042 | +0.000 |
| self_correct | Evidence chars | 20 | 299.450 | 300.000 | 299.850 | +0.150 | -0.400 | +0.550 |
| self_correct | Chunks kept | 20 | 1.400 | 1.450 | 1.050 | +0.400 | +0.350 | +0.050 |

## budget=500 (n=77)

Hierarchical dense scoring mode: `content_only`.
Hierarchical retrieval mode: `length_normalized`.
Length-normalized body window chars: `220`.

Candidate pool path-depth check:
- Gold-hier: n=30761, path_depth_mean=1.697, max=5, hist={'1': 12632, '2': 14904, '3': 3130, '4': 93, '5': 2}
- Pred-hier: n=30191, path_depth_mean=1.664, max=5, hist={'1': 13728, '2': 13052, '3': 3254, '4': 155, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.181 | 0.226 | 0.246 | -0.019 | -0.065 | +0.045 |
| MRR@chunks | 0.237 | 0.248 | 0.325 | -0.077 | -0.088 | +0.011 |
| ChunkHit@1 | 0.221 | 0.221 | 0.312 | -0.091 | -0.091 | +0.000 |
| Precision@1 line | 0.130 | 0.104 | 0.065 | +0.039 | +0.065 | -0.026 |
| Precision@3 line | 0.141 | 0.149 | 0.063 | +0.087 | +0.078 | +0.009 |
| Precision@5 line | 0.143 | 0.149 | 0.070 | +0.079 | +0.073 | +0.006 |
| MRR line | 0.187 | 0.183 | 0.143 | +0.039 | +0.044 | -0.005 |
| Hit@5 line | 0.260 | 0.273 | 0.312 | -0.039 | -0.052 | +0.013 |
| NDCG@10 line | 0.175 | 0.210 | 0.159 | +0.051 | +0.016 | +0.035 |
| Coverage line | 0.181 | 0.226 | 0.246 | -0.019 | -0.065 | +0.045 |
| Evidence chars | 499.883 | 499.338 | 499.195 | +0.143 | +0.688 | -0.545 |
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
| cross_section_conflict | Evidence chars | 9 | 500.000 | 498.667 | 500.000 | -1.333 | +0.000 | -1.333 |
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
| niche_fact | Precision@5 line | 21 | 0.147 | 0.168 | 0.069 | +0.099 | +0.078 | +0.021 |
| niche_fact | MRR line | 21 | 0.155 | 0.226 | 0.123 | +0.103 | +0.032 | +0.071 |
| niche_fact | Hit@5 line | 21 | 0.286 | 0.333 | 0.333 | +0.000 | -0.048 | +0.048 |
| niche_fact | NDCG@10 line | 21 | 0.223 | 0.271 | 0.182 | +0.089 | +0.041 | +0.048 |
| niche_fact | Coverage line | 21 | 0.230 | 0.278 | 0.333 | -0.056 | -0.103 | +0.048 |
| niche_fact | Evidence chars | 21 | 499.571 | 499.000 | 500.000 | -1.000 | -0.429 | -0.571 |
| niche_fact | Chunks kept | 21 | 2.190 | 2.095 | 1.238 | +0.857 | +0.952 | -0.095 |
| scope_collection | Coverage@budget_lenient | 15 | 0.067 | 0.167 | 0.167 | +0.000 | -0.100 | +0.100 |
| scope_collection | MRR@chunks | 15 | 0.133 | 0.200 | 0.267 | -0.067 | -0.133 | +0.067 |
| scope_collection | ChunkHit@1 | 15 | 0.133 | 0.200 | 0.267 | -0.067 | -0.133 | +0.067 |
| scope_collection | Precision@1 line | 15 | 0.133 | 0.067 | 0.000 | +0.067 | +0.133 | -0.067 |
| scope_collection | Precision@3 line | 15 | 0.100 | 0.133 | 0.056 | +0.078 | +0.044 | +0.033 |
| scope_collection | Precision@5 line | 15 | 0.100 | 0.133 | 0.073 | +0.060 | +0.027 | +0.033 |
| scope_collection | MRR line | 15 | 0.133 | 0.133 | 0.089 | +0.044 | +0.044 | +0.000 |
| scope_collection | Hit@5 line | 15 | 0.133 | 0.200 | 0.267 | -0.067 | -0.133 | +0.067 |
| scope_collection | NDCG@10 line | 15 | 0.076 | 0.164 | 0.123 | +0.041 | -0.047 | +0.088 |
| scope_collection | Coverage line | 15 | 0.067 | 0.167 | 0.167 | +0.000 | -0.100 | +0.100 |
| scope_collection | Evidence chars | 15 | 500.000 | 500.000 | 498.133 | +1.867 | +1.867 | +0.000 |
| scope_collection | Chunks kept | 15 | 1.800 | 1.800 | 1.267 | +0.533 | +0.533 | +0.000 |
| self_correct | Coverage@budget_lenient | 20 | 0.250 | 0.350 | 0.342 | +0.008 | -0.092 | +0.100 |
| self_correct | MRR@chunks | 20 | 0.225 | 0.267 | 0.375 | -0.108 | -0.150 | +0.042 |
| self_correct | ChunkHit@1 | 20 | 0.200 | 0.200 | 0.350 | -0.150 | -0.150 | +0.000 |
| self_correct | Precision@1 line | 20 | 0.100 | 0.100 | 0.050 | +0.050 | +0.050 | +0.000 |
| self_correct | Precision@3 line | 20 | 0.108 | 0.142 | 0.083 | +0.058 | +0.025 | +0.033 |
| self_correct | Precision@5 line | 20 | 0.104 | 0.142 | 0.077 | +0.065 | +0.027 | +0.037 |
| self_correct | MRR line | 20 | 0.167 | 0.199 | 0.162 | +0.037 | +0.004 | +0.032 |
| self_correct | Hit@5 line | 20 | 0.250 | 0.300 | 0.350 | -0.050 | -0.100 | +0.050 |
| self_correct | NDCG@10 line | 20 | 0.232 | 0.299 | 0.223 | +0.077 | +0.009 | +0.068 |
| self_correct | Coverage line | 20 | 0.250 | 0.350 | 0.342 | +0.008 | -0.092 | +0.100 |
| self_correct | Evidence chars | 20 | 500.000 | 499.100 | 499.350 | -0.250 | +0.650 | -0.900 |
| self_correct | Chunks kept | 20 | 1.900 | 1.800 | 1.250 | +0.550 | +0.650 | -0.100 |

## budget=1000 (n=77)

Hierarchical dense scoring mode: `content_only`.
Hierarchical retrieval mode: `length_normalized`.
Length-normalized body window chars: `220`.

Candidate pool path-depth check:
- Gold-hier: n=30761, path_depth_mean=1.697, max=5, hist={'1': 12632, '2': 14904, '3': 3130, '4': 93, '5': 2}
- Pred-hier: n=30191, path_depth_mean=1.664, max=5, hist={'1': 13728, '2': 13052, '3': 3254, '4': 155, '5': 2}
- Flat-react: flat window chunks, n=4574, no PATH

| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Coverage@budget_lenient | 0.239 | 0.324 | 0.318 | +0.005 | -0.079 | +0.084 |
| MRR@chunks | 0.268 | 0.303 | 0.398 | -0.095 | -0.131 | +0.036 |
| ChunkHit@1 | 0.234 | 0.247 | 0.364 | -0.117 | -0.130 | +0.013 |
| Precision@1 line | 0.130 | 0.104 | 0.065 | +0.039 | +0.065 | -0.026 |
| Precision@3 line | 0.113 | 0.130 | 0.061 | +0.069 | +0.052 | +0.017 |
| Precision@5 line | 0.116 | 0.131 | 0.068 | +0.063 | +0.047 | +0.016 |
| MRR line | 0.209 | 0.213 | 0.156 | +0.058 | +0.053 | +0.004 |
| Hit@5 line | 0.338 | 0.377 | 0.338 | +0.039 | +0.000 | +0.039 |
| NDCG@10 line | 0.209 | 0.260 | 0.172 | +0.088 | +0.037 | +0.051 |
| Coverage line | 0.239 | 0.324 | 0.318 | +0.005 | -0.079 | +0.084 |
| Evidence chars | 1000.000 | 1000.000 | 999.623 | +0.377 | +0.377 | +0.000 |
| Chunks kept | 2.870 | 2.987 | 2.091 | +0.896 | +0.779 | +0.117 |

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
| multi_hop | Chunks kept | 12 | 2.833 | 2.917 | 1.583 | +1.333 | +1.250 | +0.083 |
| niche_fact | Coverage@budget_lenient | 21 | 0.302 | 0.468 | 0.397 | +0.071 | -0.095 | +0.167 |
| niche_fact | MRR@chunks | 21 | 0.252 | 0.371 | 0.421 | -0.050 | -0.169 | +0.119 |
| niche_fact | ChunkHit@1 | 21 | 0.190 | 0.286 | 0.381 | -0.095 | -0.190 | +0.095 |
| niche_fact | Precision@1 line | 21 | 0.048 | 0.143 | 0.048 | +0.095 | +0.000 | +0.095 |
| niche_fact | Precision@3 line | 21 | 0.111 | 0.159 | 0.032 | +0.127 | +0.079 | +0.048 |
| niche_fact | Precision@5 line | 21 | 0.122 | 0.180 | 0.067 | +0.113 | +0.056 | +0.058 |
| niche_fact | MRR line | 21 | 0.180 | 0.287 | 0.132 | +0.156 | +0.049 | +0.107 |
| niche_fact | Hit@5 line | 21 | 0.381 | 0.524 | 0.333 | +0.190 | +0.048 | +0.143 |
| niche_fact | NDCG@10 line | 21 | 0.259 | 0.391 | 0.188 | +0.203 | +0.071 | +0.132 |
| niche_fact | Coverage line | 21 | 0.302 | 0.468 | 0.397 | +0.071 | -0.095 | +0.167 |
| niche_fact | Evidence chars | 21 | 1000.000 | 1000.000 | 999.238 | +0.762 | +0.762 | +0.000 |
| niche_fact | Chunks kept | 21 | 3.429 | 3.571 | 2.048 | +1.524 | +1.381 | +0.143 |
| scope_collection | Coverage@budget_lenient | 15 | 0.067 | 0.167 | 0.250 | -0.083 | -0.183 | +0.100 |
| scope_collection | MRR@chunks | 15 | 0.133 | 0.200 | 0.289 | -0.089 | -0.156 | +0.067 |
| scope_collection | ChunkHit@1 | 15 | 0.133 | 0.200 | 0.267 | -0.067 | -0.133 | +0.067 |
| scope_collection | Precision@1 line | 15 | 0.133 | 0.067 | 0.000 | +0.067 | +0.133 | -0.067 |
| scope_collection | Precision@3 line | 15 | 0.067 | 0.111 | 0.044 | +0.067 | +0.022 | +0.044 |
| scope_collection | Precision@5 line | 15 | 0.056 | 0.073 | 0.057 | +0.017 | -0.001 | +0.018 |
| scope_collection | MRR line | 15 | 0.133 | 0.133 | 0.093 | +0.041 | +0.041 | +0.000 |
| scope_collection | Hit@5 line | 15 | 0.133 | 0.200 | 0.267 | -0.067 | -0.133 | +0.067 |
| scope_collection | NDCG@10 line | 15 | 0.076 | 0.164 | 0.129 | +0.035 | -0.053 | +0.088 |
| scope_collection | Coverage line | 15 | 0.067 | 0.167 | 0.250 | -0.083 | -0.183 | +0.100 |
| scope_collection | Evidence chars | 15 | 1000.000 | 1000.000 | 1000.000 | +0.000 | +0.000 | +0.000 |
| scope_collection | Chunks kept | 15 | 2.733 | 2.800 | 2.333 | +0.467 | +0.400 | +0.067 |
| self_correct | Coverage@budget_lenient | 20 | 0.375 | 0.500 | 0.417 | +0.083 | -0.042 | +0.125 |
| self_correct | MRR@chunks | 20 | 0.300 | 0.362 | 0.425 | -0.062 | -0.125 | +0.062 |
| self_correct | ChunkHit@1 | 20 | 0.250 | 0.250 | 0.350 | -0.100 | -0.100 | +0.000 |
| self_correct | Precision@1 line | 20 | 0.100 | 0.100 | 0.050 | +0.050 | +0.050 | +0.000 |
| self_correct | Precision@3 line | 20 | 0.125 | 0.150 | 0.083 | +0.067 | +0.042 | +0.025 |
| self_correct | Precision@5 line | 20 | 0.134 | 0.162 | 0.070 | +0.092 | +0.064 | +0.028 |
| self_correct | MRR line | 20 | 0.212 | 0.241 | 0.171 | +0.071 | +0.041 | +0.029 |
| self_correct | Hit@5 line | 20 | 0.400 | 0.450 | 0.350 | +0.100 | +0.050 | +0.050 |
| self_correct | NDCG@10 line | 20 | 0.314 | 0.354 | 0.230 | +0.124 | +0.084 | +0.040 |
| self_correct | Coverage line | 20 | 0.375 | 0.500 | 0.417 | +0.083 | -0.042 | +0.125 |
| self_correct | Evidence chars | 20 | 1000.000 | 1000.000 | 999.350 | +0.650 | +0.650 | +0.000 |
| self_correct | Chunks kept | 20 | 2.850 | 3.050 | 2.350 | +0.700 | +0.500 | +0.200 |

