# arXiv 层级 dense scoring 模式对比

本报告只改变层级臂 dense scoring 的文本来源；Flat-react 对照保持不变。三套结果是分别输出，不做 PATH/正文加权混合。

## 实验定义

| Mode | 层级 scoring | 候选池 | 用途 |
| --- | --- | --- | --- |
| `full_text` | PATH + 正文 | 整篇文档 leaf/path pool | realdata 对齐主设置 |
| `content_only` | 仅正文 | 整篇文档 leaf/path pool | 剥离 PATH 对 dense ranking 的影响 |
| `path_only` | 仅 PATH | 整篇文档 leaf/path pool | 单独观察标题/路径文本信号 |

## 核心结论

- budget=300: Coverage@budget_lenient 最好的是 `full_text:Pred` = 0.132。
- budget=500: Coverage@budget_lenient 最好的是 `full_text:Flat` = 0.246。
- budget=1000: Coverage@budget_lenient 最好的是 `full_text:Flat` = 0.318。
- `content_only` 是最干净的正文检索诊断：PATH 不参与 dense ranking，但最终 evidence 仍保留 PATH + 正文。
- `path_only` 用来观察 section heading / path 文本本身能贡献多少信号，不建议替代主结果。

## Overall Main Metric

| Budget | Experiment | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 300 | `full_text` | 0.116 | 0.132 | 0.113 | +0.019 | +0.003 | +0.016 |
| 300 | `content_only` | 0.115 | 0.115 | 0.113 | +0.002 | +0.002 | +0.000 |
| 300 | `path_only` | 0.119 | 0.132 | 0.113 | +0.019 | +0.006 | +0.013 |
| 500 | `full_text` | 0.171 | 0.200 | 0.246 | -0.045 | -0.075 | +0.029 |
| 500 | `content_only` | 0.181 | 0.194 | 0.246 | -0.052 | -0.065 | +0.013 |
| 500 | `path_only` | 0.165 | 0.194 | 0.246 | -0.052 | -0.081 | +0.029 |
| 1000 | `full_text` | 0.216 | 0.265 | 0.318 | -0.053 | -0.102 | +0.049 |
| 1000 | `content_only` | 0.239 | 0.285 | 0.318 | -0.034 | -0.079 | +0.045 |
| 1000 | `path_only` | 0.207 | 0.226 | 0.318 | -0.092 | -0.111 | +0.019 |

## Overall All Metrics

### budget=300

| Mode | Metric | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_text` | Coverage@budget_lenient | 0.116 | 0.132 | 0.113 | +0.019 | +0.003 | +0.016 |
| `full_text` | MRR@chunks | 0.169 | 0.195 | 0.195 | +0.000 | -0.026 | +0.026 |
| `full_text` | ChunkHit@1 | 0.169 | 0.195 | 0.195 | +0.000 | -0.026 | +0.026 |
| `full_text` | Precision@1 line | 0.117 | 0.156 | 0.065 | +0.091 | +0.052 | +0.039 |
| `full_text` | Precision@3 line | 0.130 | 0.145 | 0.043 | +0.102 | +0.087 | +0.015 |
| `full_text` | Precision@5 line | 0.130 | 0.143 | 0.045 | +0.098 | +0.085 | +0.013 |
| `full_text` | MRR line | 0.143 | 0.175 | 0.106 | +0.069 | +0.036 | +0.032 |
| `full_text` | Hit@5 line | 0.169 | 0.195 | 0.195 | +0.000 | -0.026 | +0.026 |
| `full_text` | NDCG@10 line | 0.118 | 0.135 | 0.092 | +0.043 | +0.026 | +0.017 |
| `full_text` | Coverage line | 0.116 | 0.132 | 0.113 | +0.019 | +0.003 | +0.016 |
| `full_text` | Evidence chars | 300.000 | 300.000 | 299.351 | +0.649 | +0.649 | +0.000 |
| `full_text` | Chunks kept | 1.299 | 1.299 | 1.039 | +0.260 | +0.260 | +0.000 |
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
| `path_only` | Coverage@budget_lenient | 0.119 | 0.132 | 0.113 | +0.019 | +0.006 | +0.013 |
| `path_only` | MRR@chunks | 0.169 | 0.182 | 0.195 | -0.013 | -0.026 | +0.013 |
| `path_only` | ChunkHit@1 | 0.169 | 0.182 | 0.195 | -0.013 | -0.026 | +0.013 |
| `path_only` | Precision@1 line | 0.130 | 0.156 | 0.065 | +0.091 | +0.065 | +0.026 |
| `path_only` | Precision@3 line | 0.130 | 0.132 | 0.043 | +0.089 | +0.087 | +0.002 |
| `path_only` | Precision@5 line | 0.130 | 0.132 | 0.045 | +0.087 | +0.085 | +0.002 |
| `path_only` | MRR line | 0.149 | 0.169 | 0.106 | +0.062 | +0.043 | +0.019 |
| `path_only` | Hit@5 line | 0.169 | 0.182 | 0.195 | -0.013 | -0.026 | +0.013 |
| `path_only` | NDCG@10 line | 0.122 | 0.135 | 0.092 | +0.043 | +0.030 | +0.013 |
| `path_only` | Coverage line | 0.119 | 0.132 | 0.113 | +0.019 | +0.006 | +0.013 |
| `path_only` | Evidence chars | 299.948 | 300.000 | 299.351 | +0.649 | +0.597 | +0.052 |
| `path_only` | Chunks kept | 1.351 | 1.364 | 1.039 | +0.325 | +0.312 | +0.013 |

### budget=500

| Mode | Metric | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_text` | Coverage@budget_lenient | 0.171 | 0.200 | 0.246 | -0.045 | -0.075 | +0.029 |
| `full_text` | MRR@chunks | 0.221 | 0.253 | 0.325 | -0.071 | -0.104 | +0.032 |
| `full_text` | ChunkHit@1 | 0.208 | 0.234 | 0.312 | -0.078 | -0.104 | +0.026 |
| `full_text` | Precision@1 line | 0.117 | 0.156 | 0.065 | +0.091 | +0.052 | +0.039 |
| `full_text` | Precision@3 line | 0.126 | 0.152 | 0.063 | +0.089 | +0.063 | +0.026 |
| `full_text` | Precision@5 line | 0.126 | 0.150 | 0.070 | +0.080 | +0.056 | +0.024 |
| `full_text` | MRR line | 0.173 | 0.212 | 0.143 | +0.069 | +0.030 | +0.039 |
| `full_text` | Hit@5 line | 0.234 | 0.273 | 0.312 | -0.039 | -0.078 | +0.039 |
| `full_text` | NDCG@10 line | 0.169 | 0.199 | 0.159 | +0.040 | +0.010 | +0.030 |
| `full_text` | Coverage line | 0.171 | 0.200 | 0.246 | -0.045 | -0.075 | +0.029 |
| `full_text` | Evidence chars | 499.455 | 499.844 | 499.195 | +0.649 | +0.260 | +0.390 |
| `full_text` | Chunks kept | 1.805 | 1.779 | 1.273 | +0.506 | +0.532 | -0.026 |
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
| `path_only` | Coverage@budget_lenient | 0.165 | 0.194 | 0.246 | -0.052 | -0.081 | +0.029 |
| `path_only` | MRR@chunks | 0.221 | 0.240 | 0.325 | -0.084 | -0.104 | +0.019 |
| `path_only` | ChunkHit@1 | 0.208 | 0.208 | 0.312 | -0.104 | -0.104 | +0.000 |
| `path_only` | Precision@1 line | 0.130 | 0.156 | 0.065 | +0.091 | +0.065 | +0.026 |
| `path_only` | Precision@3 line | 0.128 | 0.139 | 0.063 | +0.076 | +0.065 | +0.011 |
| `path_only` | Precision@5 line | 0.128 | 0.139 | 0.070 | +0.069 | +0.058 | +0.011 |
| `path_only` | MRR line | 0.182 | 0.207 | 0.143 | +0.064 | +0.039 | +0.025 |
| `path_only` | Hit@5 line | 0.234 | 0.260 | 0.312 | -0.052 | -0.078 | +0.026 |
| `path_only` | NDCG@10 line | 0.168 | 0.187 | 0.159 | +0.029 | +0.009 | +0.020 |
| `path_only` | Coverage line | 0.165 | 0.194 | 0.246 | -0.052 | -0.081 | +0.029 |
| `path_only` | Evidence chars | 500.000 | 499.896 | 499.195 | +0.701 | +0.805 | -0.104 |
| `path_only` | Chunks kept | 1.818 | 1.805 | 1.273 | +0.532 | +0.545 | -0.013 |

### budget=1000

| Mode | Metric | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_text` | Coverage@budget_lenient | 0.216 | 0.265 | 0.318 | -0.053 | -0.102 | +0.049 |
| `full_text` | MRR@chunks | 0.246 | 0.286 | 0.398 | -0.113 | -0.153 | +0.040 |
| `full_text` | ChunkHit@1 | 0.208 | 0.247 | 0.364 | -0.117 | -0.156 | +0.039 |
| `full_text` | Precision@1 line | 0.117 | 0.156 | 0.065 | +0.091 | +0.052 | +0.039 |
| `full_text` | Precision@3 line | 0.115 | 0.117 | 0.061 | +0.056 | +0.054 | +0.002 |
| `full_text` | Precision@5 line | 0.107 | 0.111 | 0.068 | +0.043 | +0.039 | +0.005 |
| `full_text` | MRR line | 0.194 | 0.232 | 0.156 | +0.076 | +0.038 | +0.039 |
| `full_text` | Hit@5 line | 0.299 | 0.338 | 0.338 | +0.000 | -0.039 | +0.039 |
| `full_text` | NDCG@10 line | 0.196 | 0.231 | 0.172 | +0.059 | +0.024 | +0.035 |
| `full_text` | Coverage line | 0.216 | 0.265 | 0.318 | -0.053 | -0.102 | +0.049 |
| `full_text` | Evidence chars | 999.974 | 1000.000 | 999.623 | +0.377 | +0.351 | +0.026 |
| `full_text` | Chunks kept | 2.857 | 2.740 | 2.091 | +0.649 | +0.766 | -0.117 |
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
| `path_only` | Coverage@budget_lenient | 0.207 | 0.226 | 0.318 | -0.092 | -0.111 | +0.019 |
| `path_only` | MRR@chunks | 0.247 | 0.260 | 0.398 | -0.138 | -0.151 | +0.013 |
| `path_only` | ChunkHit@1 | 0.208 | 0.221 | 0.364 | -0.143 | -0.156 | +0.013 |
| `path_only` | Precision@1 line | 0.130 | 0.156 | 0.065 | +0.091 | +0.065 | +0.026 |
| `path_only` | Precision@3 line | 0.117 | 0.113 | 0.061 | +0.052 | +0.056 | -0.004 |
| `path_only` | Precision@5 line | 0.109 | 0.104 | 0.068 | +0.036 | +0.041 | -0.005 |
| `path_only` | MRR line | 0.202 | 0.221 | 0.156 | +0.065 | +0.046 | +0.019 |
| `path_only` | Hit@5 line | 0.299 | 0.299 | 0.338 | -0.039 | -0.039 | +0.000 |
| `path_only` | NDCG@10 line | 0.192 | 0.210 | 0.172 | +0.038 | +0.020 | +0.018 |
| `path_only` | Coverage line | 0.207 | 0.226 | 0.318 | -0.092 | -0.111 | +0.019 |
| `path_only` | Evidence chars | 999.870 | 999.597 | 999.623 | -0.026 | +0.247 | -0.273 |
| `path_only` | Chunks kept | 2.831 | 2.727 | 2.091 | +0.636 | +0.740 | -0.104 |

## Per-Type Coverage@budget_lenient

### budget=300

| task_type | Mode | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | `full_text` | 9 | 0.111 | 0.139 | 0.176 | -0.037 | -0.065 | +0.028 |
| cross_section_conflict | `content_only` | 9 | 0.139 | 0.028 | 0.176 | -0.148 | -0.037 | -0.111 |
| cross_section_conflict | `path_only` | 9 | 0.111 | 0.111 | 0.176 | -0.065 | -0.065 | +0.000 |
| multi_hop | `full_text` | 12 | 0.069 | 0.069 | 0.042 | +0.028 | +0.028 | +0.000 |
| multi_hop | `content_only` | 12 | 0.069 | 0.069 | 0.042 | +0.028 | +0.028 | +0.000 |
| multi_hop | `path_only` | 12 | 0.069 | 0.069 | 0.042 | +0.028 | +0.028 | +0.000 |
| niche_fact | `full_text` | 21 | 0.206 | 0.254 | 0.071 | +0.183 | +0.135 | +0.048 |
| niche_fact | `content_only` | 21 | 0.143 | 0.238 | 0.071 | +0.167 | +0.071 | +0.095 |
| niche_fact | `path_only` | 21 | 0.206 | 0.206 | 0.071 | +0.135 | +0.135 | +0.000 |
| scope_collection | `full_text` | 15 | 0.050 | 0.050 | 0.083 | -0.033 | -0.033 | +0.000 |
| scope_collection | `content_only` | 15 | 0.050 | 0.050 | 0.083 | -0.033 | -0.033 | +0.000 |
| scope_collection | `path_only` | 15 | 0.067 | 0.067 | 0.083 | -0.017 | -0.017 | +0.000 |
| self_correct | `full_text` | 20 | 0.100 | 0.100 | 0.192 | -0.092 | -0.092 | +0.000 |
| self_correct | `content_only` | 20 | 0.150 | 0.100 | 0.192 | -0.092 | -0.042 | -0.050 |
| self_correct | `path_only` | 20 | 0.100 | 0.150 | 0.192 | -0.042 | -0.092 | +0.050 |

### budget=500

| task_type | Mode | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | `full_text` | 9 | 0.111 | 0.139 | 0.176 | -0.037 | -0.065 | +0.028 |
| cross_section_conflict | `content_only` | 9 | 0.194 | 0.083 | 0.176 | -0.093 | +0.019 | -0.111 |
| cross_section_conflict | `path_only` | 9 | 0.111 | 0.139 | 0.176 | -0.037 | -0.065 | +0.028 |
| multi_hop | `full_text` | 12 | 0.111 | 0.111 | 0.083 | +0.028 | +0.028 | +0.000 |
| multi_hop | `content_only` | 12 | 0.111 | 0.111 | 0.083 | +0.028 | +0.028 | +0.000 |
| multi_hop | `path_only` | 12 | 0.111 | 0.111 | 0.083 | +0.028 | +0.028 | +0.000 |
| niche_fact | `full_text` | 21 | 0.278 | 0.278 | 0.333 | -0.056 | -0.056 | +0.000 |
| niche_fact | `content_only` | 21 | 0.230 | 0.278 | 0.333 | -0.056 | -0.103 | +0.048 |
| niche_fact | `path_only` | 21 | 0.278 | 0.230 | 0.333 | -0.103 | -0.056 | -0.048 |
| scope_collection | `full_text` | 15 | 0.067 | 0.067 | 0.167 | -0.100 | -0.100 | +0.000 |
| scope_collection | `content_only` | 15 | 0.067 | 0.067 | 0.167 | -0.100 | -0.100 | +0.000 |
| scope_collection | `path_only` | 15 | 0.067 | 0.067 | 0.167 | -0.100 | -0.100 | +0.000 |
| self_correct | `full_text` | 20 | 0.200 | 0.300 | 0.342 | -0.042 | -0.142 | +0.100 |
| self_correct | `content_only` | 20 | 0.250 | 0.300 | 0.342 | -0.042 | -0.092 | +0.050 |
| self_correct | `path_only` | 20 | 0.175 | 0.325 | 0.342 | -0.017 | -0.167 | +0.150 |

### budget=1000

| task_type | Mode | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cross_section_conflict | `full_text` | 9 | 0.167 | 0.139 | 0.176 | -0.037 | -0.009 | -0.028 |
| cross_section_conflict | `content_only` | 9 | 0.194 | 0.083 | 0.176 | -0.093 | +0.019 | -0.111 |
| cross_section_conflict | `path_only` | 9 | 0.139 | 0.139 | 0.176 | -0.037 | -0.037 | +0.000 |
| multi_hop | `full_text` | 12 | 0.111 | 0.111 | 0.208 | -0.097 | -0.097 | +0.000 |
| multi_hop | `content_only` | 12 | 0.153 | 0.153 | 0.208 | -0.056 | -0.056 | +0.000 |
| multi_hop | `path_only` | 12 | 0.111 | 0.111 | 0.208 | -0.097 | -0.097 | +0.000 |
| niche_fact | `full_text` | 21 | 0.349 | 0.397 | 0.397 | +0.000 | -0.048 | +0.048 |
| niche_fact | `content_only` | 21 | 0.302 | 0.397 | 0.397 | +0.000 | -0.095 | +0.095 |
| niche_fact | `path_only` | 21 | 0.349 | 0.349 | 0.397 | -0.048 | -0.048 | +0.000 |
| scope_collection | `full_text` | 15 | 0.067 | 0.133 | 0.250 | -0.117 | -0.183 | +0.067 |
| scope_collection | `content_only` | 15 | 0.067 | 0.133 | 0.250 | -0.117 | -0.183 | +0.067 |
| scope_collection | `path_only` | 15 | 0.067 | 0.067 | 0.250 | -0.183 | -0.183 | +0.000 |
| self_correct | `full_text` | 20 | 0.275 | 0.375 | 0.417 | -0.042 | -0.142 | +0.100 |
| self_correct | `content_only` | 20 | 0.375 | 0.450 | 0.417 | +0.033 | -0.042 | +0.075 |
| self_correct | `path_only` | 20 | 0.250 | 0.325 | 0.417 | -0.092 | -0.167 | +0.075 |
