# Bodyrich 评测交付（`delivery/` 目录）

本目录为 **bodyrich_delivery_kit** 下的评测代码与数据副本根路径。下文路径以 **本目录为根**（`data/`、`core/`、`results/`）。

主链口径：**Inspect pred-complete 97 题（hierarchical_gold / hierarchical_pred / flat 三臂 × budget 300 / 500 / 1000）**，对应任务文件 `data/tasks_realdata_bodyrich_inspect_pred_complete_97_for_runner.jsonl` 与最终产物 `results/eval97_predcomplete_postfix_b{300,500,1000}.{json,jsonl}`。

本目录是 **最终交付包**：包含评测代码（`core/agent_delivery/`）+ 主链所需数据（`data/`）+ 最终结果（`results/`）+ 独立的 arxiv 检索子包（`arxiv_aligned_retrieval_20260513/`）。如需从 `delivery/` 根目录复现，使用 `PYTHONPATH=core python3 -m agent_delivery.agent.runner_bodyrich ...`，参数见下文「评测核心代码清单」与「核心 Agent 代码导读」。

## 评测设计要点

- 对照臂：`hierarchical_gold` / `hierarchical_pred` / `flat`
- 正式代码中 `flat` 已统一替换为 Flat-ReAct，多轮 flat search + query rewrite/decomposition；旧 one-shot flat baseline 已移除。
- 按 `task_type` 看每类题的各臂表现（不丢对照）
- 支持导出每个 task 的逐题输出（JSONL）

## 整体评测流程（端到端）

1. **加载输入数据**
   - 语料：`test_jsonl`
   - 任务：`tasks_jsonl`（含 `query/doc_id/gold_nodes/gold_answer/task_type/inspect_id` 等）
2. **构建索引**
   - `hierarchical_gold`：gold tree
   - `hierarchical_pred`：pred tree（当 `pred_jsonl` 存在）
   - `flat`：flat tree
3. **逐题运行 episode**
   - hierarchical toolspace：先暴露完整 top-level map，不按 `route_m` 预裁剪 LEVEL 1；agent 自主 `get_structure` / `read_chunks(section_path)` / `search` / `finish`
   - flat：多轮 flat `search` + query rewrite/decomposition -> budget 填充 -> compose（不使用层级工具）
4. **输出映射与判分**
   - 先拿 `composed_answer`（模型输出 JSON）
   - 开启 `--inspect-judge` 时，要求每题 `inspect_id` 命中 Inspect 任务库；否则直接报错退出
   - Compose 与语义判分均强制走 LLM（读取 `core/agent_delivery/llm_api.env` 或 shell 环境变量）
5. **聚合与导出**
   - 导出每题 `rows`
   - 计算 `summary`（各臂均值、delta、per_type；由正式评测脚本产出）
   - 写汇总 JSON + 逐题 JSONL

## 评测标准（口径说明）

当前代码支持两种口径：
- `inspect_delivery_strict`：`--inspect-judge` 且逐题全部命中 Inspect
- `inspect_delivery+semantic_fallback`：Inspect 未覆盖全部逐题时的兼容口径

并且代码已改为：`--inspect-judge` 下若 registry 缺失或任务未命中 inspect_id，直接终止，不再静默回退。

- **任务分（主指标）**
  - `task_success_mean`：任务成功均值（Inspect content score 或语义回退分）
- **证据分**
  - `inspect_evidence_score_mean`：Inspect 路径下 `evidence_line_ids` 对 `gold_line_ids` 覆盖率的题级均值（逐题字段为 `inspect_evidence_score`）
- **过程分**
  - `score_process_mean` 基于轨迹长度效率与恢复情况

### Inspect 判分细则（命中 inspect_id 的题）

- 数字型金标：严格数值匹配（0/1）
- 非数字型金标：语义 LLM 打分（0~1）
- `multi_hop`：
  - `M1`：`fact_1` / `fact_2` / `final_answer` 三项平均
  - `M2`：`condition` / `outcome` / `final_answer` 三项平均
- `scope_collection` / `regulatory_coverage`：
  - 使用 gold 条目 multiset recall 作为单一内容分数，不再混合语义分或 exact 分数

### 检索指标口径提醒

- `chunk_hit@1` / `mrr_chunks`：**chunk 粒度**
- `precision@k` / `mrr_line` / `coverage_line`：**line/node 粒度**
- 两组指标反映的层级不同，不能简单一一对比
- 现存 `results/` 中：line 粒度指标位于 `rows[i].<arm>.metrics.line_retrieval` 下（内部键为 `precision@{1,3,5,8}` / `mrr` / `coverage` / `hit@5` / `ndcg@10`，**没有 `_line` 后缀**）；主 summary 指标命名保持与 `results/eval97_predcomplete_postfix_b*.json` 一致。

## 评测核心代码清单（源文件）

以下是**最小可跑评测主链**涉及的文件（已去掉旧 Agent 实验入口、数据生成脚本等）：

**包与入口**

- `core/agent_delivery/__init__.py`
- `core/agent_delivery/agent/__init__.py`
- `core/agent_delivery/code/__init__.py`

**Agent**

- `core/agent_delivery/agent/runner_bodyrich.py`
- `core/agent_delivery/agent/react_agent.py`（`hier_policy=toolspace`）
- `core/agent_delivery/agent/tasks_loader.py`（任务 JSONL → `AgentTask`）
- `core/agent_delivery/agent/types.py`

**Code**

- `core/agent_delivery/code/budget_eval.py`
- `core/agent_delivery/code/compose_llm.py`
- `core/agent_delivery/code/embedding_backend.py`
- `core/agent_delivery/code/hierarchical_tools.py`
- `core/agent_delivery/code/index_retrieval.py`
- `core/agent_delivery/code/inspect_scoring.py`
- `core/agent_delivery/code/judge_llm.py`
- `core/agent_delivery/code/llm_config.py`
- `core/agent_delivery/code/load_data.py`
- `core/agent_delivery/code/metrics.py`
- `core/agent_delivery/code/tool_space.py`

## 核心 Agent 代码导读（关键函数）

主要入口在 `core/agent_delivery/agent/runner_bodyrich.py`：

- `run_bodyrich_experiment()`：单 budget 主入口
- `run_bodyrich_experiment_multi_budget()`：多 budget 主入口（复用一次索引）
- `run_bodyrich_episode()`：单题单臂执行（route/retrieve/budget/compose）
- `_fill_agg()`：将单题结果转为可聚合指标
- `_build_summary()`：生成总表、delta、per_type

Inspect 相关核心在 `core/agent_delivery/code/inspect_scoring.py`：

- `build_inspect_pred_output()`：把模型输出映射到 Inspect 结构
- `score_sample()`：按题型执行 Inspect 评分
- `content_score_for_inspect()`：内容分底层规则（数字严格匹配 / 语义 LLM）

compose 与语义判分：

- `core/agent_delivery/code/compose_llm.py`：按题型约束输出 JSON（`answer` / `items` / `fact_*`）
- `core/agent_delivery/code/judge_llm.py`：语义任务分回退路径

## 数据文件（`data/`）

- `data/tasks_realdata_bodyrich_inspect_pred_complete_97_for_runner.jsonl`：**主链任务集（97 条）**，对应 runner 的 `--tasks`。
- `data/test_data_full_realdata_clean_merged_pred_complete.jsonl`：pred-complete 行流语料（每行含 `gold_level` 与 `predicted_level`，58 548 行 100% 覆盖），对应 runner 的 `--test_jsonl` 与 `--pred_jsonl`。
- `data/test_data_full_realdata_clean_merged.jsonl`：合并、非 pred-complete 副本，对照参考用。

Inspect 任务库（`--inspect-tasks`）已复制到 `inspect_tasks/`，包含 niche_fact / multi_hop / scope_collection 三套 Inspect JSONL。runner 默认仍会优先查找 kit 根 `datasets/realdata/` 与 `delivery_bundle_inspect_tasks/data/`，找不到时回退到 `delivery/inspect_tasks/`，因此单独携带 `delivery/` 也可以复现 Inspect 判分。

## 最终结果（`results/`）

主链产物（97 题 × 3 个 budget）：

- 汇总：`results/eval97_predcomplete_postfix_b{300,500,1000}.json`
- 逐题：`results/eval97_predcomplete_postfix_tasks_b{300,500,1000}.jsonl`

每个汇总 JSON 顶层包含：

- `summary["hierarchical_gold"]` / `summary["hierarchical_pred"]` / `summary["flat"]`：三臂均值，每个臂共 20 个键：
  - 三层评分：`score_task_mean` / `score_evidence_mean` / `score_process_mean`
  - 任务分：`task_success_mean`（主指标，Inspect content score 或语义回退分的题级均值）
  - 证据 / 检索：`evidence_hit@1_mean` / `evidence_coverage_mean` / `evidence_chars_actual_mean` / `keyword_recall_mean`
  - 过程：`process_efficiency_mean` / `process_recovery_mean` / `trajectory_length_mean` / `truncated_last_mean`
  - Inspect 聚合：`inspect_evidence_score_mean` / `inspect_content_score_mean` / `inspect_judge_used_mean`
  - Inspect 细分项（按题型在对应题上有值）：`inspect_fact_1_score_mean` / `inspect_fact_2_score_mean` / `inspect_condition_score_mean` / `inspect_outcome_score_mean` / `inspect_points_score_mean`
- `summary["per_type_hierarchical_gold"]` / `per_type_hierarchical_pred` / `per_type_flat`：按 `task_type` 拆分的同口径指标
- `summary["delta_gold_minus_flat"]` / `delta_pred_minus_flat`：Gold/Pred 减 Flat 的差值
- `rows`：97 条逐题结果，每条按 `hierarchical_gold` / `hierarchical_pred` / `flat` 三块输出 `metrics` 与 `steps`

### Summary 说明

`results/` 中的 JSON summary 是机器可读结果；`RESULTS_SUMMARY.md` 是人看的主表摘要。当前 `core/agent_delivery/` 已将 summary 指标命名对齐到现有 result JSON 文件，不再使用新版 `task_success_semantic_mean` / `inspect_evidence_mean` / `truncated_last_rate` 等命名，也不在 summary 顶层额外输出 `experiment` / `n_tasks` / `config`。

## arXiv 仅检索子包

`arxiv_aligned_retrieval_20260513/` 是独立完整的 arXiv pred-complete **仅检索** 评估包，自带 `code/`、`data_refs/`、`results/`、`README.md`、`results/summary_final.md`、`results/summary_aligned.md`，与 bodyrich 主链解耦。运行方式见该子包内的 README。
