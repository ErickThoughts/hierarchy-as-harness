# arXiv 检索改进实验汇总

范围：arXiv pred-complete 包内的 retrieval-only 诊断。Flat-react 在所有行里不变；层级臂只改变 scoring 文本或候选池构造。

## 实验定义

| Experiment | 层级 scoring | 层级候选池 | 用途 |
| --- | --- | --- | --- |
| `full_text_main` | PATH + 正文 | 整篇文档 leaf/path pool | realdata 对齐主结果 |
| `content_only` | 仅正文 | 整篇文档 leaf/path pool | 去掉 PATH 参与 dense scoring |
| `content_len220` | 仅正文 | leaf/path 正文按约 220 字符窗口切分 | 降低 chunk 长度和 budget 边界偏置 |
| `content_routed_m3` | 仅正文 | 只检索 top-3 routed sections | 强 section routing 约束 |
| `content_routed_m8` | 仅正文 | 只检索 top-8 routed sections | 较宽松 section routing 约束 |

## 核心结论

- `content_len220` 是当前唯一明确有效的改进诊断：budget=1000 时 Pred-hier=0.324，略高于 Flat-react=0.318。
- Routing 不适合作为主设置：`content_routed_m8` 在 budget=1000 的 Pred-hier=0.239，低于 full-pool 和 Flat-react，说明当前 top-section router 召回损失较大。
- Gold-hier 仍没有稳定超过 Pred-hier；主结果 budget=1000 为 Gold=0.216, Pred=0.265。这更像 tree/chunk 边界对 dense retrieval 的影响，而不是 PATH 文本单独造成的偏置。
- 正式汇报建议：`full_text_main` 作为 realdata 对齐主结果；`content_only` 和 `content_len220` 作为诊断/改进补充。

## Main Metric: Coverage@budget_lenient

| Budget | Experiment | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 300 | `full_text_main` | 0.116 | 0.132 | 0.113 | +0.019 | +0.003 | +0.016 |
| 300 | `content_only` | 0.115 | 0.115 | 0.113 | +0.002 | +0.002 | +0.000 |
| 300 | `content_len220` | 0.115 | 0.141 | 0.113 | +0.028 | +0.002 | +0.026 |
| 300 | `content_routed_m3` | 0.093 | 0.087 | 0.113 | -0.026 | -0.019 | -0.006 |
| 300 | `content_routed_m8` | 0.102 | 0.089 | 0.113 | -0.024 | -0.011 | -0.013 |
| 500 | `full_text_main` | 0.171 | 0.200 | 0.246 | -0.045 | -0.075 | +0.029 |
| 500 | `content_only` | 0.181 | 0.194 | 0.246 | -0.052 | -0.065 | +0.013 |
| 500 | `content_len220` | 0.181 | 0.226 | 0.246 | -0.019 | -0.065 | +0.045 |
| 500 | `content_routed_m3` | 0.148 | 0.135 | 0.246 | -0.110 | -0.097 | -0.013 |
| 500 | `content_routed_m8` | 0.148 | 0.142 | 0.246 | -0.104 | -0.097 | -0.006 |
| 1000 | `full_text_main` | 0.216 | 0.265 | 0.318 | -0.053 | -0.102 | +0.049 |
| 1000 | `content_only` | 0.239 | 0.285 | 0.318 | -0.034 | -0.079 | +0.045 |
| 1000 | `content_len220` | 0.239 | 0.324 | 0.318 | +0.005 | -0.079 | +0.084 |
| 1000 | `content_routed_m3` | 0.181 | 0.207 | 0.318 | -0.111 | -0.137 | +0.026 |
| 1000 | `content_routed_m8` | 0.213 | 0.239 | 0.318 | -0.079 | -0.105 | +0.026 |

## Overall All Metrics

### budget=300

| Experiment | Metric | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_text_main` | Coverage@budget_lenient | 0.116 | 0.132 | 0.113 | +0.019 | +0.003 | +0.016 |
| `full_text_main` | MRR@chunks | 0.169 | 0.195 | 0.195 | +0.000 | -0.026 | +0.026 |
| `full_text_main` | ChunkHit@1 | 0.169 | 0.195 | 0.195 | +0.000 | -0.026 | +0.026 |
| `full_text_main` | Precision@1 line | 0.117 | 0.156 | 0.065 | +0.091 | +0.052 | +0.039 |
| `full_text_main` | Precision@3 line | 0.130 | 0.145 | 0.043 | +0.102 | +0.087 | +0.015 |
| `full_text_main` | Precision@5 line | 0.130 | 0.143 | 0.045 | +0.098 | +0.085 | +0.013 |
| `full_text_main` | MRR line | 0.143 | 0.175 | 0.106 | +0.069 | +0.036 | +0.032 |
| `full_text_main` | Hit@5 line | 0.169 | 0.195 | 0.195 | +0.000 | -0.026 | +0.026 |
| `full_text_main` | NDCG@10 line | 0.118 | 0.135 | 0.092 | +0.043 | +0.026 | +0.017 |
| `full_text_main` | Coverage line | 0.116 | 0.132 | 0.113 | +0.019 | +0.003 | +0.016 |
| `full_text_main` | Evidence chars | 300.000 | 300.000 | 299.351 | +0.649 | +0.649 | +0.000 |
| `full_text_main` | Chunks kept | 1.299 | 1.299 | 1.039 | +0.260 | +0.260 | +0.000 |
| `content_only` | Coverage@budget_lenient | 0.115 | 0.115 | 0.113 | +0.002 | +0.002 | +0.000 |
| `content_only` | MRR@chunks | 0.169 | 0.156 | 0.195 | -0.039 | -0.026 | -0.013 |
| `content_only` | ChunkHit@1 | 0.169 | 0.156 | 0.195 | -0.039 | -0.026 | -0.013 |
| `content_only` | Precision@1 line | 0.130 | 0.117 | 0.065 | +0.052 | +0.065 | -0.013 |
| `content_only` | Precision@3 line | 0.136 | 0.121 | 0.043 | +0.078 | +0.093 | -0.015 |
| `content_only` | Precision@5 line | 0.136 | 0.119 | 0.045 | +0.074 | +0.091 | -0.017 |
| `content_only` | MRR line | 0.149 | 0.136 | 0.106 | +0.030 | +0.043 | -0.013 |
| `content_only` | Hit@5 line | 0.169 | 0.156 | 0.195 | -0.039 | -0.026 | -0.013 |
| `content_only` | NDCG@10 line | 0.117 | 0.117 | 0.092 | +0.025 | +0.025 | +0.000 |
| `content_only` | Coverage line | 0.115 | 0.115 | 0.113 | +0.002 | +0.002 | +0.000 |
| `content_only` | Evidence chars | 299.753 | 300.000 | 299.351 | +0.649 | +0.403 | +0.247 |
| `content_only` | Chunks kept | 1.416 | 1.377 | 1.039 | +0.338 | +0.377 | -0.039 |
| `content_len220` | Coverage@budget_lenient | 0.115 | 0.141 | 0.113 | +0.028 | +0.002 | +0.026 |
| `content_len220` | MRR@chunks | 0.169 | 0.182 | 0.195 | -0.013 | -0.026 | +0.013 |
| `content_len220` | ChunkHit@1 | 0.169 | 0.182 | 0.195 | -0.013 | -0.026 | +0.013 |
| `content_len220` | Precision@1 line | 0.130 | 0.104 | 0.065 | +0.039 | +0.065 | -0.026 |
| `content_len220` | Precision@3 line | 0.136 | 0.126 | 0.043 | +0.082 | +0.093 | -0.011 |
| `content_len220` | Precision@5 line | 0.136 | 0.124 | 0.045 | +0.079 | +0.091 | -0.013 |
| `content_len220` | MRR line | 0.149 | 0.143 | 0.106 | +0.036 | +0.043 | -0.006 |
| `content_len220` | Hit@5 line | 0.169 | 0.182 | 0.195 | -0.013 | -0.026 | +0.013 |
| `content_len220` | NDCG@10 line | 0.117 | 0.143 | 0.092 | +0.051 | +0.025 | +0.026 |
| `content_len220` | Coverage line | 0.115 | 0.141 | 0.113 | +0.028 | +0.002 | +0.026 |
| `content_len220` | Evidence chars | 299.857 | 300.000 | 299.351 | +0.649 | +0.506 | +0.143 |
| `content_len220` | Chunks kept | 1.416 | 1.403 | 1.039 | +0.364 | +0.377 | -0.013 |
| `content_routed_m3` | Coverage@budget_lenient | 0.093 | 0.087 | 0.113 | -0.026 | -0.019 | -0.006 |
| `content_routed_m3` | MRR@chunks | 0.147 | 0.134 | 0.195 | -0.061 | -0.048 | -0.013 |
| `content_routed_m3` | ChunkHit@1 | 0.143 | 0.130 | 0.195 | -0.065 | -0.052 | -0.013 |
| `content_routed_m3` | Precision@1 line | 0.143 | 0.117 | 0.065 | +0.052 | +0.078 | -0.026 |
| `content_routed_m3` | Precision@3 line | 0.128 | 0.115 | 0.043 | +0.071 | +0.084 | -0.013 |
| `content_routed_m3` | Precision@5 line | 0.128 | 0.115 | 0.045 | +0.070 | +0.083 | -0.013 |
| `content_routed_m3` | MRR line | 0.147 | 0.128 | 0.106 | +0.021 | +0.041 | -0.019 |
| `content_routed_m3` | Hit@5 line | 0.156 | 0.143 | 0.195 | -0.052 | -0.039 | -0.013 |
| `content_routed_m3` | NDCG@10 line | 0.094 | 0.088 | 0.092 | -0.004 | +0.002 | -0.006 |
| `content_routed_m3` | Coverage line | 0.093 | 0.087 | 0.113 | -0.026 | -0.019 | -0.006 |
| `content_routed_m3` | Evidence chars | 298.156 | 298.961 | 299.351 | -0.390 | -1.195 | +0.805 |
| `content_routed_m3` | Chunks kept | 1.468 | 1.429 | 1.039 | +0.390 | +0.429 | -0.039 |
| `content_routed_m8` | Coverage@budget_lenient | 0.102 | 0.089 | 0.113 | -0.024 | -0.011 | -0.013 |
| `content_routed_m8` | MRR@chunks | 0.156 | 0.130 | 0.195 | -0.065 | -0.039 | -0.026 |
| `content_routed_m8` | ChunkHit@1 | 0.156 | 0.130 | 0.195 | -0.065 | -0.039 | -0.026 |
| `content_routed_m8` | Precision@1 line | 0.143 | 0.104 | 0.065 | +0.039 | +0.078 | -0.039 |
| `content_routed_m8` | Precision@3 line | 0.130 | 0.102 | 0.043 | +0.058 | +0.087 | -0.028 |
| `content_routed_m8` | Precision@5 line | 0.130 | 0.100 | 0.045 | +0.055 | +0.085 | -0.030 |
| `content_routed_m8` | MRR line | 0.149 | 0.117 | 0.106 | +0.010 | +0.043 | -0.032 |
| `content_routed_m8` | Hit@5 line | 0.156 | 0.130 | 0.195 | -0.065 | -0.039 | -0.026 |
| `content_routed_m8` | NDCG@10 line | 0.104 | 0.091 | 0.092 | -0.001 | +0.012 | -0.013 |
| `content_routed_m8` | Coverage line | 0.102 | 0.089 | 0.113 | -0.024 | -0.011 | -0.013 |
| `content_routed_m8` | Evidence chars | 299.584 | 299.364 | 299.351 | +0.013 | +0.234 | -0.221 |
| `content_routed_m8` | Chunks kept | 1.429 | 1.351 | 1.039 | +0.312 | +0.390 | -0.078 |

### budget=500

| Experiment | Metric | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_text_main` | Coverage@budget_lenient | 0.171 | 0.200 | 0.246 | -0.045 | -0.075 | +0.029 |
| `full_text_main` | MRR@chunks | 0.221 | 0.253 | 0.325 | -0.071 | -0.104 | +0.032 |
| `full_text_main` | ChunkHit@1 | 0.208 | 0.234 | 0.312 | -0.078 | -0.104 | +0.026 |
| `full_text_main` | Precision@1 line | 0.117 | 0.156 | 0.065 | +0.091 | +0.052 | +0.039 |
| `full_text_main` | Precision@3 line | 0.126 | 0.152 | 0.063 | +0.089 | +0.063 | +0.026 |
| `full_text_main` | Precision@5 line | 0.126 | 0.150 | 0.070 | +0.080 | +0.056 | +0.024 |
| `full_text_main` | MRR line | 0.173 | 0.212 | 0.143 | +0.069 | +0.030 | +0.039 |
| `full_text_main` | Hit@5 line | 0.234 | 0.273 | 0.312 | -0.039 | -0.078 | +0.039 |
| `full_text_main` | NDCG@10 line | 0.169 | 0.199 | 0.159 | +0.040 | +0.010 | +0.030 |
| `full_text_main` | Coverage line | 0.171 | 0.200 | 0.246 | -0.045 | -0.075 | +0.029 |
| `full_text_main` | Evidence chars | 499.455 | 499.844 | 499.195 | +0.649 | +0.260 | +0.390 |
| `full_text_main` | Chunks kept | 1.805 | 1.779 | 1.273 | +0.506 | +0.532 | -0.026 |
| `content_only` | Coverage@budget_lenient | 0.181 | 0.194 | 0.246 | -0.052 | -0.065 | +0.013 |
| `content_only` | MRR@chunks | 0.237 | 0.231 | 0.325 | -0.094 | -0.088 | -0.006 |
| `content_only` | ChunkHit@1 | 0.221 | 0.208 | 0.312 | -0.104 | -0.091 | -0.013 |
| `content_only` | Precision@1 line | 0.130 | 0.117 | 0.065 | +0.052 | +0.065 | -0.013 |
| `content_only` | Precision@3 line | 0.141 | 0.143 | 0.063 | +0.080 | +0.078 | +0.002 |
| `content_only` | Precision@5 line | 0.143 | 0.143 | 0.070 | +0.073 | +0.073 | +0.000 |
| `content_only` | MRR line | 0.187 | 0.181 | 0.143 | +0.038 | +0.044 | -0.006 |
| `content_only` | Hit@5 line | 0.260 | 0.260 | 0.312 | -0.052 | -0.052 | +0.000 |
| `content_only` | NDCG@10 line | 0.175 | 0.188 | 0.159 | +0.029 | +0.016 | +0.013 |
| `content_only` | Coverage line | 0.181 | 0.194 | 0.246 | -0.052 | -0.065 | +0.013 |
| `content_only` | Evidence chars | 499.831 | 499.623 | 499.195 | +0.429 | +0.636 | -0.208 |
| `content_only` | Chunks kept | 1.883 | 1.818 | 1.273 | +0.545 | +0.610 | -0.065 |
| `content_len220` | Coverage@budget_lenient | 0.181 | 0.226 | 0.246 | -0.019 | -0.065 | +0.045 |
| `content_len220` | MRR@chunks | 0.237 | 0.248 | 0.325 | -0.077 | -0.088 | +0.011 |
| `content_len220` | ChunkHit@1 | 0.221 | 0.221 | 0.312 | -0.091 | -0.091 | +0.000 |
| `content_len220` | Precision@1 line | 0.130 | 0.104 | 0.065 | +0.039 | +0.065 | -0.026 |
| `content_len220` | Precision@3 line | 0.141 | 0.149 | 0.063 | +0.087 | +0.078 | +0.009 |
| `content_len220` | Precision@5 line | 0.143 | 0.149 | 0.070 | +0.079 | +0.073 | +0.006 |
| `content_len220` | MRR line | 0.187 | 0.183 | 0.143 | +0.039 | +0.044 | -0.005 |
| `content_len220` | Hit@5 line | 0.260 | 0.273 | 0.312 | -0.039 | -0.052 | +0.013 |
| `content_len220` | NDCG@10 line | 0.175 | 0.210 | 0.159 | +0.051 | +0.016 | +0.035 |
| `content_len220` | Coverage line | 0.181 | 0.226 | 0.246 | -0.019 | -0.065 | +0.045 |
| `content_len220` | Evidence chars | 499.883 | 499.338 | 499.195 | +0.143 | +0.688 | -0.545 |
| `content_len220` | Chunks kept | 1.883 | 1.818 | 1.273 | +0.545 | +0.610 | -0.065 |
| `content_routed_m3` | Coverage@budget_lenient | 0.148 | 0.135 | 0.246 | -0.110 | -0.097 | -0.013 |
| `content_routed_m3` | MRR@chunks | 0.199 | 0.180 | 0.325 | -0.145 | -0.126 | -0.019 |
| `content_routed_m3` | ChunkHit@1 | 0.182 | 0.156 | 0.312 | -0.156 | -0.130 | -0.026 |
| `content_routed_m3` | Precision@1 line | 0.143 | 0.117 | 0.065 | +0.052 | +0.078 | -0.026 |
| `content_routed_m3` | Precision@3 line | 0.132 | 0.121 | 0.063 | +0.058 | +0.069 | -0.011 |
| `content_routed_m3` | Precision@5 line | 0.132 | 0.121 | 0.070 | +0.051 | +0.062 | -0.011 |
| `content_routed_m3` | MRR line | 0.180 | 0.160 | 0.143 | +0.017 | +0.036 | -0.019 |
| `content_routed_m3` | Hit@5 line | 0.221 | 0.208 | 0.312 | -0.104 | -0.091 | -0.013 |
| `content_routed_m3` | NDCG@10 line | 0.150 | 0.137 | 0.159 | -0.021 | -0.008 | -0.013 |
| `content_routed_m3` | Coverage line | 0.148 | 0.135 | 0.246 | -0.110 | -0.097 | -0.013 |
| `content_routed_m3` | Evidence chars | 490.286 | 493.766 | 499.195 | -5.429 | -8.909 | +3.481 |
| `content_routed_m3` | Chunks kept | 1.909 | 1.896 | 1.273 | +0.623 | +0.636 | -0.013 |
| `content_routed_m8` | Coverage@budget_lenient | 0.148 | 0.142 | 0.246 | -0.104 | -0.097 | -0.006 |
| `content_routed_m8` | MRR@chunks | 0.205 | 0.179 | 0.325 | -0.146 | -0.120 | -0.026 |
| `content_routed_m8` | ChunkHit@1 | 0.195 | 0.156 | 0.312 | -0.156 | -0.117 | -0.039 |
| `content_routed_m8` | Precision@1 line | 0.143 | 0.104 | 0.065 | +0.039 | +0.078 | -0.039 |
| `content_routed_m8` | Precision@3 line | 0.128 | 0.117 | 0.063 | +0.054 | +0.065 | -0.011 |
| `content_routed_m8` | Precision@5 line | 0.130 | 0.117 | 0.070 | +0.047 | +0.060 | -0.013 |
| `content_routed_m8` | MRR line | 0.179 | 0.153 | 0.143 | +0.009 | +0.035 | -0.026 |
| `content_routed_m8` | Hit@5 line | 0.221 | 0.208 | 0.312 | -0.104 | -0.091 | -0.013 |
| `content_routed_m8` | NDCG@10 line | 0.150 | 0.143 | 0.159 | -0.016 | -0.009 | -0.006 |
| `content_routed_m8` | Coverage line | 0.148 | 0.142 | 0.246 | -0.104 | -0.097 | -0.006 |
| `content_routed_m8` | Evidence chars | 499.831 | 499.623 | 499.195 | +0.429 | +0.636 | -0.208 |
| `content_routed_m8` | Chunks kept | 1.948 | 1.870 | 1.273 | +0.597 | +0.675 | -0.078 |

### budget=1000

| Experiment | Metric | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_text_main` | Coverage@budget_lenient | 0.216 | 0.265 | 0.318 | -0.053 | -0.102 | +0.049 |
| `full_text_main` | MRR@chunks | 0.246 | 0.286 | 0.398 | -0.113 | -0.153 | +0.040 |
| `full_text_main` | ChunkHit@1 | 0.208 | 0.247 | 0.364 | -0.117 | -0.156 | +0.039 |
| `full_text_main` | Precision@1 line | 0.117 | 0.156 | 0.065 | +0.091 | +0.052 | +0.039 |
| `full_text_main` | Precision@3 line | 0.115 | 0.117 | 0.061 | +0.056 | +0.054 | +0.002 |
| `full_text_main` | Precision@5 line | 0.107 | 0.111 | 0.068 | +0.043 | +0.039 | +0.005 |
| `full_text_main` | MRR line | 0.194 | 0.232 | 0.156 | +0.076 | +0.038 | +0.039 |
| `full_text_main` | Hit@5 line | 0.299 | 0.338 | 0.338 | +0.000 | -0.039 | +0.039 |
| `full_text_main` | NDCG@10 line | 0.196 | 0.231 | 0.172 | +0.059 | +0.024 | +0.035 |
| `full_text_main` | Coverage line | 0.216 | 0.265 | 0.318 | -0.053 | -0.102 | +0.049 |
| `full_text_main` | Evidence chars | 999.974 | 1000.000 | 999.623 | +0.377 | +0.351 | +0.026 |
| `full_text_main` | Chunks kept | 2.857 | 2.740 | 2.091 | +0.649 | +0.766 | -0.117 |
| `content_only` | Coverage@budget_lenient | 0.239 | 0.285 | 0.318 | -0.034 | -0.079 | +0.045 |
| `content_only` | MRR@chunks | 0.268 | 0.290 | 0.398 | -0.108 | -0.131 | +0.023 |
| `content_only` | ChunkHit@1 | 0.234 | 0.247 | 0.364 | -0.117 | -0.130 | +0.013 |
| `content_only` | Precision@1 line | 0.130 | 0.117 | 0.065 | +0.052 | +0.065 | -0.013 |
| `content_only` | Precision@3 line | 0.113 | 0.123 | 0.061 | +0.063 | +0.052 | +0.011 |
| `content_only` | Precision@5 line | 0.114 | 0.121 | 0.068 | +0.053 | +0.046 | +0.008 |
| `content_only` | MRR line | 0.209 | 0.213 | 0.156 | +0.057 | +0.053 | +0.004 |
| `content_only` | Hit@5 line | 0.338 | 0.364 | 0.338 | +0.026 | +0.000 | +0.026 |
| `content_only` | NDCG@10 line | 0.209 | 0.236 | 0.172 | +0.064 | +0.037 | +0.027 |
| `content_only` | Coverage line | 0.239 | 0.285 | 0.318 | -0.034 | -0.079 | +0.045 |
| `content_only` | Evidence chars | 1000.000 | 1000.000 | 999.623 | +0.377 | +0.377 | +0.000 |
| `content_only` | Chunks kept | 2.870 | 2.909 | 2.091 | +0.818 | +0.779 | +0.039 |
| `content_len220` | Coverage@budget_lenient | 0.239 | 0.324 | 0.318 | +0.005 | -0.079 | +0.084 |
| `content_len220` | MRR@chunks | 0.268 | 0.303 | 0.398 | -0.095 | -0.131 | +0.036 |
| `content_len220` | ChunkHit@1 | 0.234 | 0.247 | 0.364 | -0.117 | -0.130 | +0.013 |
| `content_len220` | Precision@1 line | 0.130 | 0.104 | 0.065 | +0.039 | +0.065 | -0.026 |
| `content_len220` | Precision@3 line | 0.113 | 0.130 | 0.061 | +0.069 | +0.052 | +0.017 |
| `content_len220` | Precision@5 line | 0.116 | 0.131 | 0.068 | +0.063 | +0.047 | +0.016 |
| `content_len220` | MRR line | 0.209 | 0.213 | 0.156 | +0.058 | +0.053 | +0.004 |
| `content_len220` | Hit@5 line | 0.338 | 0.377 | 0.338 | +0.039 | +0.000 | +0.039 |
| `content_len220` | NDCG@10 line | 0.209 | 0.260 | 0.172 | +0.088 | +0.037 | +0.051 |
| `content_len220` | Coverage line | 0.239 | 0.324 | 0.318 | +0.005 | -0.079 | +0.084 |
| `content_len220` | Evidence chars | 1000.000 | 1000.000 | 999.623 | +0.377 | +0.377 | +0.000 |
| `content_len220` | Chunks kept | 2.870 | 2.987 | 2.091 | +0.896 | +0.779 | +0.117 |
| `content_routed_m3` | Coverage@budget_lenient | 0.181 | 0.207 | 0.318 | -0.111 | -0.137 | +0.026 |
| `content_routed_m3` | MRR@chunks | 0.216 | 0.225 | 0.398 | -0.173 | -0.182 | +0.009 |
| `content_routed_m3` | ChunkHit@1 | 0.182 | 0.182 | 0.364 | -0.182 | -0.182 | +0.000 |
| `content_routed_m3` | Precision@1 line | 0.143 | 0.117 | 0.065 | +0.052 | +0.078 | -0.026 |
| `content_routed_m3` | Precision@3 line | 0.104 | 0.110 | 0.061 | +0.050 | +0.043 | +0.006 |
| `content_routed_m3` | Precision@5 line | 0.110 | 0.107 | 0.068 | +0.039 | +0.042 | -0.003 |
| `content_routed_m3` | MRR line | 0.195 | 0.188 | 0.156 | +0.032 | +0.039 | -0.007 |
| `content_routed_m3` | Hit@5 line | 0.273 | 0.286 | 0.338 | -0.052 | -0.065 | +0.013 |
| `content_routed_m3` | NDCG@10 line | 0.168 | 0.177 | 0.172 | +0.005 | -0.004 | +0.009 |
| `content_routed_m3` | Coverage line | 0.181 | 0.207 | 0.318 | -0.111 | -0.137 | +0.026 |
| `content_routed_m3` | Evidence chars | 880.545 | 904.610 | 999.623 | -95.013 | -119.078 | +24.065 |
| `content_routed_m3` | Chunks kept | 2.519 | 2.545 | 2.091 | +0.455 | +0.429 | +0.026 |
| `content_routed_m8` | Coverage@budget_lenient | 0.213 | 0.239 | 0.318 | -0.079 | -0.105 | +0.026 |
| `content_routed_m8` | MRR@chunks | 0.242 | 0.242 | 0.398 | -0.156 | -0.156 | +0.000 |
| `content_routed_m8` | ChunkHit@1 | 0.208 | 0.195 | 0.364 | -0.169 | -0.156 | -0.013 |
| `content_routed_m8` | Precision@1 line | 0.143 | 0.104 | 0.065 | +0.039 | +0.078 | -0.039 |
| `content_routed_m8` | Precision@3 line | 0.113 | 0.115 | 0.061 | +0.054 | +0.052 | +0.002 |
| `content_routed_m8` | Precision@5 line | 0.109 | 0.104 | 0.068 | +0.035 | +0.041 | -0.006 |
| `content_routed_m8` | MRR line | 0.208 | 0.189 | 0.156 | +0.033 | +0.052 | -0.020 |
| `content_routed_m8` | Hit@5 line | 0.312 | 0.312 | 0.338 | -0.026 | -0.026 | +0.000 |
| `content_routed_m8` | NDCG@10 line | 0.192 | 0.199 | 0.172 | +0.027 | +0.020 | +0.007 |
| `content_routed_m8` | Coverage line | 0.213 | 0.239 | 0.318 | -0.079 | -0.105 | +0.026 |
| `content_routed_m8` | Evidence chars | 999.974 | 999.792 | 999.623 | +0.169 | +0.351 | -0.182 |
| `content_routed_m8` | Chunks kept | 3.156 | 3.156 | 2.091 | +1.065 | +1.065 | +0.000 |

## Per-Type Coverage@budget_lenient

### budget=300

| task_type | Experiment | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | `full_text_main` | 9 | 0.111 | 0.139 | 0.176 | -0.037 | -0.065 | +0.028 |
| cross_section_conflict | `content_only` | 9 | 0.139 | 0.028 | 0.176 | -0.148 | -0.037 | -0.111 |
| cross_section_conflict | `content_len220` | 9 | 0.139 | 0.028 | 0.176 | -0.148 | -0.037 | -0.111 |
| cross_section_conflict | `content_routed_m3` | 9 | 0.139 | 0.028 | 0.176 | -0.148 | -0.037 | -0.111 |
| cross_section_conflict | `content_routed_m8` | 9 | 0.139 | 0.028 | 0.176 | -0.148 | -0.037 | -0.111 |
| multi_hop | `full_text_main` | 12 | 0.069 | 0.069 | 0.042 | +0.028 | +0.028 | +0.000 |
| multi_hop | `content_only` | 12 | 0.069 | 0.069 | 0.042 | +0.028 | +0.028 | +0.000 |
| multi_hop | `content_len220` | 12 | 0.069 | 0.069 | 0.042 | +0.028 | +0.028 | +0.000 |
| multi_hop | `content_routed_m3` | 12 | 0.069 | 0.069 | 0.042 | +0.028 | +0.028 | +0.000 |
| multi_hop | `content_routed_m8` | 12 | 0.069 | 0.069 | 0.042 | +0.028 | +0.028 | +0.000 |
| niche_fact | `full_text_main` | 21 | 0.206 | 0.254 | 0.071 | +0.183 | +0.135 | +0.048 |
| niche_fact | `content_only` | 21 | 0.143 | 0.238 | 0.071 | +0.167 | +0.071 | +0.095 |
| niche_fact | `content_len220` | 21 | 0.143 | 0.238 | 0.071 | +0.167 | +0.071 | +0.095 |
| niche_fact | `content_routed_m3` | 21 | 0.063 | 0.063 | 0.071 | -0.008 | -0.008 | +0.000 |
| niche_fact | `content_routed_m8` | 21 | 0.095 | 0.095 | 0.071 | +0.024 | +0.024 | +0.000 |
| scope_collection | `full_text_main` | 15 | 0.050 | 0.050 | 0.083 | -0.033 | -0.033 | +0.000 |
| scope_collection | `content_only` | 15 | 0.050 | 0.050 | 0.083 | -0.033 | -0.033 | +0.000 |
| scope_collection | `content_len220` | 15 | 0.050 | 0.117 | 0.083 | +0.033 | -0.033 | +0.067 |
| scope_collection | `content_routed_m3` | 15 | 0.050 | 0.050 | 0.083 | -0.033 | -0.033 | +0.000 |
| scope_collection | `content_routed_m8` | 15 | 0.050 | 0.050 | 0.083 | -0.033 | -0.033 | +0.000 |
| self_correct | `full_text_main` | 20 | 0.100 | 0.100 | 0.192 | -0.092 | -0.092 | +0.000 |
| self_correct | `content_only` | 20 | 0.150 | 0.100 | 0.192 | -0.092 | -0.042 | -0.050 |
| self_correct | `content_len220` | 20 | 0.150 | 0.150 | 0.192 | -0.042 | -0.042 | +0.000 |
| self_correct | `content_routed_m3` | 20 | 0.150 | 0.175 | 0.192 | -0.017 | -0.042 | +0.025 |
| self_correct | `content_routed_m8` | 20 | 0.150 | 0.150 | 0.192 | -0.042 | -0.042 | +0.000 |

### budget=500

| task_type | Experiment | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | `full_text_main` | 9 | 0.111 | 0.139 | 0.176 | -0.037 | -0.065 | +0.028 |
| cross_section_conflict | `content_only` | 9 | 0.194 | 0.083 | 0.176 | -0.093 | +0.019 | -0.111 |
| cross_section_conflict | `content_len220` | 9 | 0.194 | 0.083 | 0.176 | -0.093 | +0.019 | -0.111 |
| cross_section_conflict | `content_routed_m3` | 9 | 0.139 | 0.028 | 0.176 | -0.148 | -0.037 | -0.111 |
| cross_section_conflict | `content_routed_m8` | 9 | 0.139 | 0.028 | 0.176 | -0.148 | -0.037 | -0.111 |
| multi_hop | `full_text_main` | 12 | 0.111 | 0.111 | 0.083 | +0.028 | +0.028 | +0.000 |
| multi_hop | `content_only` | 12 | 0.111 | 0.111 | 0.083 | +0.028 | +0.028 | +0.000 |
| multi_hop | `content_len220` | 12 | 0.111 | 0.111 | 0.083 | +0.028 | +0.028 | +0.000 |
| multi_hop | `content_routed_m3` | 12 | 0.111 | 0.111 | 0.083 | +0.028 | +0.028 | +0.000 |
| multi_hop | `content_routed_m8` | 12 | 0.111 | 0.111 | 0.083 | +0.028 | +0.028 | +0.000 |
| niche_fact | `full_text_main` | 21 | 0.278 | 0.278 | 0.333 | -0.056 | -0.056 | +0.000 |
| niche_fact | `content_only` | 21 | 0.230 | 0.278 | 0.333 | -0.056 | -0.103 | +0.048 |
| niche_fact | `content_len220` | 21 | 0.230 | 0.278 | 0.333 | -0.056 | -0.103 | +0.048 |
| niche_fact | `content_routed_m3` | 21 | 0.135 | 0.087 | 0.333 | -0.246 | -0.198 | -0.048 |
| niche_fact | `content_routed_m8` | 21 | 0.183 | 0.135 | 0.333 | -0.198 | -0.151 | -0.048 |
| scope_collection | `full_text_main` | 15 | 0.067 | 0.067 | 0.167 | -0.100 | -0.100 | +0.000 |
| scope_collection | `content_only` | 15 | 0.067 | 0.067 | 0.167 | -0.100 | -0.100 | +0.000 |
| scope_collection | `content_len220` | 15 | 0.067 | 0.167 | 0.167 | +0.000 | -0.100 | +0.100 |
| scope_collection | `content_routed_m3` | 15 | 0.067 | 0.067 | 0.167 | -0.100 | -0.100 | +0.000 |
| scope_collection | `content_routed_m8` | 15 | 0.067 | 0.067 | 0.167 | -0.100 | -0.100 | +0.000 |
| self_correct | `full_text_main` | 20 | 0.200 | 0.300 | 0.342 | -0.042 | -0.142 | +0.100 |
| self_correct | `content_only` | 20 | 0.250 | 0.300 | 0.342 | -0.042 | -0.092 | +0.050 |
| self_correct | `content_len220` | 20 | 0.250 | 0.350 | 0.342 | +0.008 | -0.092 | +0.100 |
| self_correct | `content_routed_m3` | 20 | 0.250 | 0.300 | 0.342 | -0.042 | -0.092 | +0.050 |
| self_correct | `content_routed_m8` | 20 | 0.200 | 0.275 | 0.342 | -0.067 | -0.142 | +0.075 |

### budget=1000

| task_type | Experiment | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | `full_text_main` | 9 | 0.167 | 0.139 | 0.176 | -0.037 | -0.009 | -0.028 |
| cross_section_conflict | `content_only` | 9 | 0.194 | 0.083 | 0.176 | -0.093 | +0.019 | -0.111 |
| cross_section_conflict | `content_len220` | 9 | 0.194 | 0.083 | 0.176 | -0.093 | +0.019 | -0.111 |
| cross_section_conflict | `content_routed_m3` | 9 | 0.139 | 0.083 | 0.176 | -0.093 | -0.037 | -0.056 |
| cross_section_conflict | `content_routed_m8` | 9 | 0.139 | 0.028 | 0.176 | -0.148 | -0.037 | -0.111 |
| multi_hop | `full_text_main` | 12 | 0.111 | 0.111 | 0.208 | -0.097 | -0.097 | +0.000 |
| multi_hop | `content_only` | 12 | 0.153 | 0.153 | 0.208 | -0.056 | -0.056 | +0.000 |
| multi_hop | `content_len220` | 12 | 0.153 | 0.153 | 0.208 | -0.056 | -0.056 | +0.000 |
| multi_hop | `content_routed_m3` | 12 | 0.111 | 0.111 | 0.208 | -0.097 | -0.097 | +0.000 |
| multi_hop | `content_routed_m8` | 12 | 0.111 | 0.111 | 0.208 | -0.097 | -0.097 | +0.000 |
| niche_fact | `full_text_main` | 21 | 0.349 | 0.397 | 0.397 | +0.000 | -0.048 | +0.048 |
| niche_fact | `content_only` | 21 | 0.302 | 0.397 | 0.397 | +0.000 | -0.095 | +0.095 |
| niche_fact | `content_len220` | 21 | 0.302 | 0.468 | 0.397 | +0.071 | -0.095 | +0.167 |
| niche_fact | `content_routed_m3` | 21 | 0.206 | 0.206 | 0.397 | -0.190 | -0.190 | +0.000 |
| niche_fact | `content_routed_m8` | 21 | 0.254 | 0.254 | 0.397 | -0.143 | -0.143 | +0.000 |
| scope_collection | `full_text_main` | 15 | 0.067 | 0.133 | 0.250 | -0.117 | -0.183 | +0.067 |
| scope_collection | `content_only` | 15 | 0.067 | 0.133 | 0.250 | -0.117 | -0.183 | +0.067 |
| scope_collection | `content_len220` | 15 | 0.067 | 0.167 | 0.250 | -0.083 | -0.183 | +0.100 |
| scope_collection | `content_routed_m3` | 15 | 0.067 | 0.167 | 0.250 | -0.083 | -0.183 | +0.100 |
| scope_collection | `content_routed_m8` | 15 | 0.100 | 0.167 | 0.250 | -0.083 | -0.150 | +0.067 |
| self_correct | `full_text_main` | 20 | 0.275 | 0.375 | 0.417 | -0.042 | -0.142 | +0.100 |
| self_correct | `content_only` | 20 | 0.375 | 0.450 | 0.417 | +0.033 | -0.042 | +0.075 |
| self_correct | `content_len220` | 20 | 0.375 | 0.500 | 0.417 | +0.083 | -0.042 | +0.125 |
| self_correct | `content_routed_m3` | 20 | 0.300 | 0.350 | 0.417 | -0.067 | -0.117 | +0.050 |
| self_correct | `content_routed_m8` | 20 | 0.350 | 0.450 | 0.417 | +0.033 | -0.067 | +0.100 |
